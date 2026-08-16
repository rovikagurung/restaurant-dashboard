from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from xlsx_reader import read_xlsx_bytes, rows_to_dicts

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "restaurant.db"
SAMPLE_DIR = BASE / "sample-data"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="RestoSight")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

# Recipe / management assumptions.
# One pizza uses 100 g = 0.10 kg of cheese.
PIZZA_CHEESE_KG_PER_ITEM = 0.10
CHEESE_ITEM_WORDS = ("mozzarella", "cheese")
APP_TIMEZONE = ZoneInfo("Asia/Kathmandu")


def local_today_iso():
    return datetime.now(APP_TIMEZONE).date().isoformat()


def date_obj(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


SECRET_PATH = DATA_DIR / ".session_secret"
if SECRET_PATH.exists():
    SESSION_SECRET = SECRET_PATH.read_bytes()
else:
    SESSION_SECRET = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(SESSION_SECRET)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
    return base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, digest_b64 = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        candidate = hash_password(password, salt).split("$", 1)[1]
        return hmac.compare_digest(candidate, digest_b64)
    except Exception:
        return False


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('owner','manager','head_employee')),
                branch_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL,
                upload_date TEXT NOT NULL,
                file_type TEXT NOT NULL CHECK(file_type IN ('purchase','daybook','sales','sold_items','inventory')),
                original_name TEXT NOT NULL,
                stored_path TEXT,
                sheet_name TEXT,
                headers_json TEXT NOT NULL,
                rows_json TEXT NOT NULL,
                uploaded_by INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL,
                UNIQUE(branch_id, upload_date, file_type)
            );
            CREATE TABLE IF NOT EXISTS stock_thresholds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                minimum_qty REAL NOT NULL DEFAULT 0,
                unit TEXT DEFAULT '',
                UNIQUE(branch_id, item_name)
            );
            CREATE TABLE IF NOT EXISTS dish_photo_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL,
                upload_date TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                rows_json TEXT NOT NULL,
                uploaded_by INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL,
                UNIQUE(branch_id, upload_date, file_hash)
            );
            """
        )
        # Upgrade older databases so Sold Items can be stored as a fourth Excel type.
        upload_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='uploads'").fetchone()
        if upload_sql and ("sold_items" not in (upload_sql["sql"] or "") or "inventory" not in (upload_sql["sql"] or "")):
            conn.executescript(
                """
                ALTER TABLE uploads RENAME TO uploads_legacy;
                CREATE TABLE uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    branch_id INTEGER NOT NULL,
                    upload_date TEXT NOT NULL,
                    file_type TEXT NOT NULL CHECK(file_type IN ('purchase','daybook','sales','sold_items','inventory')),
                    original_name TEXT NOT NULL,
                    stored_path TEXT,
                    sheet_name TEXT,
                    headers_json TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    uploaded_by INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    UNIQUE(branch_id, upload_date, file_type)
                );
                INSERT INTO uploads(id,branch_id,upload_date,file_type,original_name,stored_path,sheet_name,headers_json,rows_json,uploaded_by,uploaded_at)
                SELECT id,branch_id,upload_date,file_type,original_name,stored_path,sheet_name,headers_json,rows_json,uploaded_by,uploaded_at FROM uploads_legacy;
                DROP TABLE uploads_legacy;
                """
            )

        defaults = {
            "branch_1_name": "Branch 1",
            "branch_2_name": "Branch 2",
            "restaurant_name": "Your Restaurant",
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))

        # RestoSight is the platform brand; the restaurant name remains editable
        # in Settings. Only migrate the old built-in default, never a custom name.
        conn.execute(
            "UPDATE settings SET value='Your Restaurant' "
            "WHERE key='restaurant_name' AND value='Restaurant Command Center'"
        )
        users = [
            ("owner", "Owner / Admin", "Owner@123", "owner", None),
            ("manager1", "Branch 1 Manager", "Manager@123", "manager", 1),
            ("head2", "Branch 2 Head Employee", "Head@123", "head_employee", 2),
        ]
        for username, name, pw, role, branch in users:
            conn.execute(
                "INSERT OR IGNORE INTO users(username,display_name,password_hash,role,branch_id,active,created_at) VALUES(?,?,?,?,?,1,?)",
                (username, name, hash_password(pw), role, branch, datetime.now().isoformat(timespec="seconds")),
            )


init_db()


def settings_dict():
    with db() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM settings")}


def sign_session(user_id: int) -> str:
    payload = json.dumps({"uid": user_id, "exp": int(time.time()) + 60 * 60 * 12}, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(payload).rstrip(b"=")
    sig = hmac.new(SESSION_SECRET, body, hashlib.sha256).digest()
    return body.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def unsign_session(token: str):
    try:
        body_s, sig_s = token.split(".", 1)
        body = body_s.encode()
        expected = hmac.new(SESSION_SECRET, body, hashlib.sha256).digest()
        sig = base64.urlsafe_b64decode(sig_s + "=" * (-len(sig_s) % 4))
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body_s + "=" * (-len(body_s) % 4)))
        if payload["exp"] < time.time():
            return None
        return int(payload["uid"])
    except Exception:
        return None


def current_user(request: Request):
    token = request.cookies.get("restaurant_session")
    uid = unsign_session(token) if token else None
    if not uid:
        raise HTTPException(401, "Please log in.")
    with db() as conn:
        row = conn.execute("SELECT id,username,display_name,role,branch_id,active FROM users WHERE id=?", (uid,)).fetchone()
    if not row or not row["active"]:
        raise HTTPException(401, "Account is inactive.")
    return dict(row)


def can_access_branch(user, branch_id: int):
    return user["role"] == "owner" or user["branch_id"] == branch_id


def clean_header(v):
    return re.sub(r"[^a-z0-9]+", "", str(v or "").lower())


def find_key(headers, candidates):
    cmap = {clean_header(h): h for h in headers}
    # exact normalized match first
    for c in candidates:
        n = clean_header(c)
        if n in cmap:
            return cmap[n]
    # then containment
    for h in headers:
        hn = clean_header(h)
        for c in candidates:
            cn = clean_header(c)
            if cn and (cn in hn or hn in cn):
                return h
    return None


def number(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v).replace(",", ""))
    try:
        return float(s) if s not in ("", "-", ".") else 0.0
    except Exception:
        return 0.0


def iso_date(v, fallback=None):
    if v in (None, ""):
        return fallback
    if isinstance(v, (int, float)) and v > 30000:
        # Excel serial date, 1899-12-30 convention
        from datetime import timedelta
        return (datetime(1899, 12, 30) + timedelta(days=float(v))).date().isoformat()
    s = str(v).strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return fallback or s


def parse_upload_bytes(content: bytes):
    parsed = read_xlsx_bytes(content)
    headers, rows = rows_to_dicts(parsed["rows"])
    return parsed["sheet_name"], headers, rows


def _has_nonempty_value(rows, key):
    if not key:
        return False
    return any(row.get(key) not in (None, "", "-") for row in rows)


def validate_upload_structure(file_type: str, headers, rows):
    """Reject a workbook when it does not match the selected upload type.

    Validation happens before the file is written to disk or saved to SQLite.
    The checks intentionally use common aliases so normal restaurant exports keep
    working while obvious cross-uploads (e.g. Sold Items in the Sales box) fail.
    """
    if not headers:
        raise HTTPException(400, "The workbook has no readable column headers.")
    if not rows:
        raise HTTPException(400, "The workbook has no readable data rows.")

    if file_type == "sold_items":
        item_k = find_key(headers, ["dish name", "menu item", "item name", "food item", "item", "product", "particulars"])
        qty_k = find_key(headers, ["qty sold", "quantity sold", "qty", "quantity", "units sold", "sold qty", "sold"])
        amount_k = find_key(headers, ["sales amount", "amount", "net sales", "revenue", "total amount", "sales"])
        if not (item_k and qty_k and _has_nonempty_value(rows, item_k)):
            raise HTTPException(400, "Wrong file for Sold Items. Expected columns such as Dish Name and QTY.")
        if not amount_k:
            raise HTTPException(400, "Wrong file for Sold Items. An Amount/Sales column is also required.")
        return

    if file_type == "inventory":
        item_k = find_key(headers, ["item name", "stock item", "ingredient", "material", "product", "item"])
        stock_k = find_key(headers, ["closing stock", "closing qty", "available qty", "stock qty", "current stock", "balance qty", "stock"])
        if not (item_k and stock_k and _has_nonempty_value(rows, item_k)):
            raise HTTPException(400, "Wrong file for Inventory. Expected Item Name and Current Stock/Closing Stock columns.")
        return

    if file_type == "purchase":
        amount_k = find_key(headers, ["TNX Amount (NPR)", "txn amount", "purchase amount", "total amount", "amount"])
        head_k = find_key(headers, ["account head", "category", "purchase category", "expense head", "expense category"])
        if not (amount_k and head_k and _has_nonempty_value(rows, head_k)):
            raise HTTPException(400, "Wrong file for Purchase / Expense. Expected Account Head/Expense Category and Amount columns.")
        return

    if file_type == "sales":
        amount_k = find_key(headers, ["TXN AMOUNT (NPR)", "txn amount", "net sales", "net amount", "amount", "grand total", "total amount"])
        identity_keys = [
            find_key(headers, ["id", "invoice", "invoice no", "bill no", "ticket no", "voucher no"]),
            find_key(headers, ["status", "payment status"]),
            find_key(headers, ["mode", "payment mode", "payment method"]),
            find_key(headers, ["order type", "service type"]),
            find_key(headers, ["billed by", "cashier", "staff", "employee"]),
        ]
        if not amount_k or not any(identity_keys):
            raise HTTPException(400, "Wrong file for Sales. Expected a sales amount plus invoice/ticket, payment, order-type, or cashier columns.")
        return

    if file_type == "daybook":
        label_k = headers[0] if headers else None
        recognized = {
            clean_header("NetSales"), clean_header("Net Sales"),
            clean_header("Total Receipts"), clean_header("Credit"), clean_header("Credit Sales"), clean_header("Expenses"),
            clean_header("Total Payments"), clean_header("Net Receipts"),
            clean_header("Closing Balance"), clean_header("Difference"),
            clean_header("Finance - Daybook Difference"),
        }
        found = set()
        if label_k:
            for row in rows:
                label = clean_header(row.get(label_k))
                for target in recognized:
                    if label == target or (target and target in label):
                        found.add(target)
        if len(found) < 2:
            raise HTTPException(400, "Wrong file for Daybook. Expected Daybook rows such as NetSales, Total Receipts, Expenses, or Closing Balance.")
        return


def fetch_uploads(branch_ids, start=None, end=None, file_type=None):
    q = "SELECT * FROM uploads WHERE branch_id IN (%s)" % ",".join("?" for _ in branch_ids)
    params = list(branch_ids)
    if start:
        q += " AND upload_date>=?"; params.append(start)
    if end:
        q += " AND upload_date<=?"; params.append(end)
    if file_type:
        q += " AND file_type=?"; params.append(file_type)
    q += " ORDER BY upload_date, id"
    with db() as conn:
        rows = conn.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["headers"] = json.loads(d.pop("headers_json"))
        d["rows"] = json.loads(d.pop("rows_json"))
        out.append(d)
    return out


def sum_map(d):
    return [{"label": k, "value": round(v, 2)} for k, v in sorted(d.items(), key=lambda x: x[1], reverse=True)]


def summarize_sold_items(uploads):
    qty = defaultdict(float)
    sales = defaultdict(float)
    display = {}
    rows_count = 0
    for up in uploads:
        headers = up["headers"]
        name_k = find_key(headers, ["dish name", "menu item", "item name", "food item", "item", "product", "particulars"])
        qty_k = find_key(headers, ["qty sold", "quantity sold", "qty", "quantity", "units sold", "sold qty", "sold"])
        sales_k = find_key(headers, ["sales amount", "amount", "net sales", "revenue", "total amount", "sales"])
        if not name_k:
            continue
        for row in up["rows"]:
            name = str(row.get(name_k) or "").strip()
            if not name or name == "-":
                continue
            key = clean_header(name) or name.lower()
            display.setdefault(key, name)
            qty[key] += number(row.get(qty_k)) if qty_k else 0
            sales[key] += number(row.get(sales_k)) if sales_k else 0
            rows_count += 1
    total_sales = sum(sales.values())
    ranked = sorted(qty.keys(), key=lambda k: (qty[k], sales[k]), reverse=True)
    dishes = [
        {
            "name": display[k],
            "qty": round(qty[k], 2),
            "sales": round(sales[k], 2),
            "pct": round((sales[k] / total_sales * 100) if total_sales else 0, 2),
        }
        for k in ranked
    ]
    return {
        "dishes": dishes,
        "qty_total": round(sum(qty.values()), 2),
        "sales_total": round(total_sales, 2),
        "upload_count": len(uploads),
        "rows_count": rows_count,
    }


def summarize_sales(uploads, sold_item_uploads=None):
    total = paid = unpaid = 0.0
    bills = set()
    order_types = defaultdict(float); payment_modes = defaultdict(float); staff = defaultdict(float)
    daily = defaultdict(float); dishes_qty = defaultdict(float); dishes_sales = defaultdict(float)
    rows_count = 0
    for up in uploads:
        headers = up["headers"]
        amount_k = find_key(headers, ["TXN AMOUNT (NPR)", "txn amount", "net sales", "net amount", "amount", "grand total", "total amount"])
        status_k = find_key(headers, ["status", "payment status"])
        id_k = find_key(headers, ["id", "invoice", "invoice no", "bill no", "voucher no"])
        date_k = find_key(headers, ["txn date", "date", "invoice date", "bill date"])
        order_k = find_key(headers, ["order type", "type", "service type"])
        mode_k = find_key(headers, ["mode", "payment mode", "payment method"])
        staff_k = find_key(headers, ["billed by", "cashier", "staff", "employee"])
        item_k = find_key(headers, ["dish name", "menu item", "item name", "item", "product", "particulars"])
        qty_k = find_key(headers, ["qty sold", "quantity", "qty", "units"])
        for row in up["rows"]:
            rows_count += 1
            amt = number(row.get(amount_k)) if amount_k else 0
            total += amt
            st = str(row.get(status_k, "")).strip().lower() if status_k else ""
            if st in ("paid", "complete", "completed", "settled"):
                paid += amt
            elif st:
                unpaid += amt
            else:
                paid += amt
            bill = str(row.get(id_k) or f"{up['id']}:{rows_count}") if id_k else f"{up['id']}:{rows_count}"
            bills.add(f"{up['branch_id']}:{bill}")
            d = iso_date(row.get(date_k), up["upload_date"]) if date_k else up["upload_date"]
            daily[d] += amt
            if order_k and row.get(order_k) not in (None, ""):
                order_types[str(row.get(order_k)).strip()] += amt
            if mode_k and row.get(mode_k) not in (None, "", "-"):
                payment_modes[str(row.get(mode_k)).strip()] += amt
            if staff_k and row.get(staff_k) not in (None, ""):
                staff[str(row.get(staff_k)).strip()] += amt
            if item_k and row.get(item_k) not in (None, "", "-"):
                item = str(row.get(item_k)).strip()
                q = number(row.get(qty_k)) if qty_k else 1
                dishes_qty[item] += q
                dishes_sales[item] += amt
    dish_rank = sorted(dishes_qty.items(), key=lambda x: x[1], reverse=True)
    excel_dishes = [{"name": k, "qty": round(v,2), "sales": round(dishes_sales[k],2), "pct": 0} for k,v in dish_rank]
    sold_summary = summarize_sold_items(sold_item_uploads or [])
    if sold_summary["dishes"]:
        dish_rows = sold_summary["dishes"]
        dish_source = "sold_items"
    else:
        dish_rows = excel_dishes
        dish_source = "sales_excel" if excel_dishes else None
        if dish_rows:
            dish_total = sum(x["sales"] for x in dish_rows)
            for x in dish_rows:
                x["pct"] = round((x["sales"] / dish_total * 100) if dish_total else 0, 2)
    return {
        "total": round(total, 2), "paid": round(paid, 2), "unpaid": round(unpaid, 2),
        "bills": len(bills), "tickets": len(bills), "avg_bill": round(total / len(bills), 2) if bills else 0,
        "daily": [{"date": k, "value": round(v,2)} for k,v in sorted(daily.items())],
        "order_types": sum_map(order_types), "payment_modes": sum_map(payment_modes), "staff": sum_map(staff),
        "dishes": dish_rows,
        "has_dish_data": bool(dish_rows),
        "dish_source": dish_source,
        "dish_sales_total": sold_summary["sales_total"] if sold_summary["dishes"] else round(sum(x["sales"] for x in excel_dishes), 2),
        "dish_qty_total": sold_summary["qty_total"] if sold_summary["dishes"] else round(sum(x["qty"] for x in excel_dishes),2),
        "dish_upload_count": sold_summary["upload_count"],
        "dish_rows_count": sold_summary["rows_count"],
    }

def summarize_purchase(uploads):
    total = 0.0; heads = defaultdict(float); accounts = defaultdict(float); daily = defaultdict(float); lines=[]
    for up in uploads:
        h = up["headers"]
        amount_k = find_key(h, ["TNX Amount (NPR)", "txn amount", "purchase amount", "total amount", "amount"])
        head_k = find_key(h, ["account head", "category", "purchase category", "expense head"])
        acc_k = find_key(h, ["account", "payment account"])
        date_k = find_key(h, ["txn date", "date", "purchase date"])
        rem_k = find_key(h, ["remarks", "description", "particulars"])
        for row in up["rows"]:
            amt = number(row.get(amount_k)) if amount_k else 0
            total += amt
            d=iso_date(row.get(date_k), up["upload_date"]) if date_k else up["upload_date"]
            daily[d]+=amt
            if head_k and row.get(head_k) not in (None,""): heads[str(row.get(head_k)).strip()] += amt
            if acc_k and row.get(acc_k) not in (None,""): accounts[str(row.get(acc_k)).strip()] += amt
            if len(lines)<30:
                lines.append({"date":d,"head":str(row.get(head_k) or "-"),"remarks":str(row.get(rem_k) or "-"),"amount":round(amt,2),"branch_id":up["branch_id"]})
    return {"total":round(total,2),"heads":sum_map(heads),"accounts":sum_map(accounts),"daily":[{"date":k,"value":round(v,2)} for k,v in sorted(daily.items())],"lines":lines}


def daybook_value(up, labels):
    headers=up["headers"]
    if not headers: return None
    label_k=headers[0]
    total_k=find_key(headers,["Total","Total Amount","Net","Value","Amount"])
    targets=[clean_header(x) for x in labels]
    matched=None
    # Exact normalized match first, then allow the requested label to be contained
    # in decorated labels such as "Closing Balance [E = C + D]".
    for row in up["rows"]:
        n=clean_header(str(row.get(label_k) or ""))
        if n in targets:
            matched=row; break
    if matched is None:
        for row in up["rows"]:
            n=clean_header(str(row.get(label_k) or ""))
            if any(t and t in n for t in targets):
                matched=row; break
    if matched is None: return None
    total_val=number(matched.get(total_k)) if total_k else 0.0
    try:
        total_idx=headers.index(total_k) if total_k else len(headers)
    except ValueError:
        total_idx=len(headers)
    account_sum=sum(number(matched.get(h)) for h in headers[1:total_idx])
    # Some exports leave the Total cell as 0 even while payment-account columns
    # contain the actual value (e.g. Expenses). Prefer a non-zero total; otherwise
    # fall back to the account-column sum.
    if abs(total_val) > 1e-12: return total_val
    if abs(account_sum) > 1e-12: return account_sum
    return total_val


def summarize_daybook(uploads):
    daily=[]
    for up in uploads:
        net_sales=daybook_value(up,["NetSales","Net Sales"])
        receipts=daybook_value(up,["Total Receipts"])
        expenses=daybook_value(up,["Expenses"])
        payments=daybook_value(up,["Total Payments"])
        net_receipts=daybook_value(up,["Net Receipts"])
        closing_balance=daybook_value(up,["Closing Balance"])
        difference=daybook_value(up,["Difference","Finance - Daybook Difference"])
        credit=daybook_value(up,["Credit","Credit Sales","Credit / Due","Due Sales","Outstanding Sales"])

        # If the Daybook does not contain a dedicated Credit row, derive the
        # uncollected portion of sales from Net Sales minus Total Receipts.
        if credit is None and net_sales is not None and receipts is not None:
            credit=max(number(net_sales)-number(receipts),0.0)

        daily.append({
            "date":up["upload_date"],"branch_id":up["branch_id"],
            "net_sales":net_sales,
            "receipts":receipts,
            "expenses":expenses,
            "credit":credit,
            "payments":payments,
            "net_receipts":net_receipts,
            "closing_balance":closing_balance,
            "difference":difference,
        })
    if daily:
        latest_date=max(x["date"] for x in daily)
        latest_rows=[x for x in daily if x["date"]==latest_date]
        latest={"date":latest_date,"branch_id":latest_rows[0]["branch_id"] if len(latest_rows)==1 else None}
        for key in ("net_sales","receipts","credit","expenses","payments","net_receipts","closing_balance","difference"):
            vals=[x[key] for x in latest_rows if x.get(key) is not None]
            latest[key]=sum(vals) if vals else None
    else:
        latest={}
    return {"daily":daily,"latest":latest}


def inventory_from_uploads(uploads, branch_ids):
    """Return the newest inventory snapshot for each selected branch.

    Expected columns (common aliases are accepted):
      Item Name | Current Stock | Minimum Stock | Target Stock | Unit

    Target Stock is optional. If it is missing, the target defaults to
    2 × Minimum Stock. The order list is created only for LOW/OUT items.
    """
    candidates=[]
    for branch_id in branch_ids:
        branch_candidates=[]
        branch_uploads=[u for u in uploads if u["branch_id"]==branch_id]
        inventory_uploads=[u for u in branch_uploads if u["file_type"]=="inventory"]
        stock_sources=inventory_uploads if inventory_uploads else branch_uploads

        for up in sorted(stock_sources, key=lambda x:(x["upload_date"],x["id"]), reverse=True):
            h=up["headers"]
            item_k=find_key(h,["item name","stock item","ingredient","material","product","item"])
            stock_k=find_key(h,["closing stock","closing qty","available qty","stock qty","current stock","balance qty","stock"])
            min_k=find_key(h,["minimum qty","min stock","reorder level","reorder qty","minimum stock"])
            target_k=find_key(h,["target stock","desired stock","maximum stock","max stock","par stock","ideal stock"])
            unit_k=find_key(h,["unit","uom"])
            if not (item_k and stock_k):
                continue

            for row in up["rows"]:
                item=row.get(item_k)
                if item in (None,"", "-"):
                    continue
                min_raw=row.get(min_k) if min_k else None
                target_raw=row.get(target_k) if target_k else None
                minimum=None if min_raw in (None,"") else number(min_raw)
                target=None if target_raw in (None,"") else number(target_raw)
                branch_candidates.append({
                    "branch_id":up["branch_id"],
                    "item":str(item).strip(),
                    "qty":number(row.get(stock_k)),
                    "minimum":minimum,
                    "target":target,
                    "unit":str(row.get(unit_k) or "") if unit_k else "",
                    "date":up["upload_date"],
                })
            if branch_candidates:
                break
        candidates.extend(branch_candidates)

    # Merge manually saved minimum thresholds when Excel does not provide them.
    with db() as conn:
        placeholders=",".join("?" for _ in branch_ids)
        rows=conn.execute(
            f"SELECT * FROM stock_thresholds WHERE branch_id IN ({placeholders})",
            branch_ids,
        )
        thresholds={
            (r["branch_id"],r["item_name"].lower()):(r["minimum_qty"],r["unit"] or "")
            for r in rows
        }

    alerts=[]
    order_list=[]
    for r in candidates:
        if r["minimum"] is None:
            t=thresholds.get((r["branch_id"],r["item"].lower()))
            if t:
                r["minimum"],r["unit"]=t[0],r["unit"] or t[1]

        # If Target Stock is not supplied, use twice the minimum as a practical par level.
        if r["target"] is None and r["minimum"] is not None:
            r["target"]=round(max(r["minimum"],r["minimum"]*2),2)
        elif r["target"] is not None and r["minimum"] is not None:
            r["target"]=max(r["target"],r["minimum"])

        if r["minimum"] is not None:
            if r["qty"] <= 0:
                status="out"
            elif r["qty"] <= r["minimum"]:
                status="low"
            else:
                status="ok"
        else:
            status="unknown"

        r["status"]=status
        r["order_qty"]=round(max((r["target"] or 0)-r["qty"],0),2) if status in ("low","out") else 0
        alerts.append(r)
        if status in ("low","out"):
            order_list.append(dict(r))

    rank={"out":0,"low":1,"ok":2,"unknown":3}
    alerts.sort(key=lambda x:(rank.get(x["status"],9),x["branch_id"],x["item"].lower()))
    order_list.sort(key=lambda x:(rank.get(x["status"],9),x["branch_id"],-x["order_qty"],x["item"].lower()))
    return {
        "items":alerts,
        "order_list":order_list,
        "has_stock_data":bool(candidates),
        "low_count":sum(1 for x in alerts if x["status"]=="low"),
        "out_count":sum(1 for x in alerts if x["status"]=="out"),
        "order_count":len(order_list),
    }


def calculate_ingredient_usage(sales):
    """Estimate cheese usage from Sold Items / dish sales.

    Current rule: every dish whose name contains 'pizza' uses 0.10 kg cheese.
    This is an estimate for management planning, not a stock ledger deduction.
    """
    pizza_qty=0.0
    pizza_sales=0.0
    pizza_items=[]
    for dish in sales.get("dishes",[]):
        name=str(dish.get("name") or "")
        if "pizza" in name.lower():
            qty=number(dish.get("qty"))
            amount=number(dish.get("sales"))
            pizza_qty+=qty
            pizza_sales+=amount
            pizza_items.append({"name":name,"qty":round(qty,2),"sales":round(amount,2)})
    return {
        "pizza_qty":round(pizza_qty,2),
        "pizza_sales":round(pizza_sales,2),
        "cheese_used_kg":round(pizza_qty*PIZZA_CHEESE_KG_PER_ITEM,2),
        "cheese_per_pizza_kg":PIZZA_CHEESE_KG_PER_ITEM,
        "pizza_items":pizza_items,
    }


def find_cheese_stock(inventory, branch_id=None):
    items=inventory.get("items",[]) if inventory else []
    if branch_id is not None:
        items=[x for x in items if x.get("branch_id")==branch_id]
    matches=[]
    for item in items:
        n=clean_header(item.get("item"))
        score=0
        if "mozzarella" in n:
            score=2
        elif "cheese" in n:
            score=1
        if score:
            matches.append((score,item))
    if not matches:
        return None
    matches.sort(key=lambda x:(-x[0],x[1].get("item","").lower()))
    return matches[0][1]


def branch_metrics(branch_id, start=None, end=None):
    ups=fetch_uploads([branch_id],start,end)
    sales=summarize_sales(
        [u for u in ups if u["file_type"]=="sales"],
        [u for u in ups if u["file_type"]=="sold_items"],
    )
    inventory=inventory_from_uploads(ups,[branch_id])
    return {
        "branch_id":branch_id,
        "sales":sales,
        "purchase":summarize_purchase([u for u in ups if u["file_type"]=="purchase"]),
        "daybook":summarize_daybook([u for u in ups if u["file_type"]=="daybook"]),
        "inventory":inventory,
        "ingredient_usage":calculate_ingredient_usage(sales),
    }


def build_management(sales, inventory, branches):
    """Structured management facts used by dashboard highlights and owner welcome."""
    s = settings_dict()
    dishes = sales.get("dishes", []) or []
    positive = [x for x in dishes if number(x.get("qty")) > 0]
    highest_qty = max(positive, key=lambda x: (number(x.get("qty")), number(x.get("sales")))) if positive else None
    lowest_qty = min(positive, key=lambda x: (number(x.get("qty")), number(x.get("sales")))) if positive else None
    highest_revenue = max(positive, key=lambda x: number(x.get("sales"))) if positive else None

    usage = calculate_ingredient_usage(sales)
    combined_sales = round(sum(number(b.get("sales", {}).get("total")) for b in branches), 2)

    branch_summary = []
    cheese_remaining_total = 0.0
    cheese_remaining_known = False

    for b in branches:
        b_dishes = b.get("sales", {}).get("dishes", []) or []
        b_positive = [x for x in b_dishes if number(x.get("qty")) > 0]
        b_top = max(b_positive, key=lambda x: (number(x.get("qty")), number(x.get("sales")))) if b_positive else None
        b_low = min(b_positive, key=lambda x: (number(x.get("qty")), number(x.get("sales")))) if b_positive else None

        inv = b.get("inventory", {})
        cheese = find_cheese_stock(inv, b.get("branch_id"))
        cheese_usage = b.get("ingredient_usage", {}).get("cheese_used_kg", 0)
        cheese_detail = None

        if cheese:
            cheese_remaining_known = True
            cheese_remaining_total += number(cheese.get("qty"))
            cheese_detail = {
                "item": cheese.get("item"),
                "current": round(number(cheese.get("qty")), 2),
                "minimum": cheese.get("minimum"),
                "target": cheese.get("target"),
                "unit": cheese.get("unit") or "kg",
                "status": cheese.get("status"),
                "order_qty": round(number(cheese.get("order_qty")), 2),
                "needed_to_target": round(max(number(cheese.get("target")) - number(cheese.get("qty")), 0), 2) if cheese.get("target") is not None else 0,
            }

        branch_summary.append({
            "branch_id": b.get("branch_id"),
            "branch_name": s.get(f"branch_{b.get('branch_id')}_name", f"Branch {b.get('branch_id')}"),
            "sales": round(number(b.get("sales", {}).get("total")), 2),
            "items_sold": round(number(b.get("sales", {}).get("dish_qty_total")), 2),
            "top_item": b_top,
            "lowest_item": b_low,
            "pizza_qty": round(number(b.get("ingredient_usage", {}).get("pizza_qty")), 2),
            "cheese_used_kg": round(number(cheese_usage), 2),
            "cheese_stock": cheese_detail,
            "low_stock_count": inv.get("low_count", 0),
            "out_stock_count": inv.get("out_count", 0),
        })

    highest_sales_branch = max(branch_summary, key=lambda x: x["sales"]) if branch_summary else None

    daily_map = {
        date_obj(x.get("date")): number(x.get("value"))
        for x in sales.get("daily", [])
        if date_obj(x.get("date"))
    }
    latest_date = max(daily_map.keys()) if daily_map else None
    week_comparison = None
    weekday_comparison = None

    if latest_date:
        last_week_start = latest_date - timedelta(days=6)
        previous_week_end = last_week_start - timedelta(days=1)
        previous_week_start = previous_week_end - timedelta(days=6)
        last_week_sales = sum(value for day, value in daily_map.items() if last_week_start <= day <= latest_date)
        previous_week_sales = sum(value for day, value in daily_map.items() if previous_week_start <= day <= previous_week_end)
        change_pct = ((last_week_sales - previous_week_sales) / previous_week_sales) * 100 if previous_week_sales else None

        week_comparison = {
            "latest_date": latest_date.isoformat(),
            "current_start": last_week_start.isoformat(),
            "current_end": latest_date.isoformat(),
            "previous_start": previous_week_start.isoformat(),
            "previous_end": previous_week_end.isoformat(),
            "current_sales": round(last_week_sales, 2),
            "previous_sales": round(previous_week_sales, 2),
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
        }

        same_weekdays = sorted(
            [(day, value) for day, value in daily_map.items()
             if day.year == latest_date.year and day.month == latest_date.month and day.weekday() == latest_date.weekday()],
            key=lambda x: x[0]
        )
        if same_weekdays:
            values = [x[1] for x in same_weekdays]
            current_value = daily_map.get(latest_date, 0)
            max_value = max(values)
            sorted_desc = sorted(values, reverse=True)
            rank = sorted_desc.index(current_value) + 1 if current_value in sorted_desc else None
            weekday_comparison = {
                "weekday": latest_date.strftime("%A"),
                "date": latest_date.isoformat(),
                "sales": round(current_value, 2),
                "count": len(same_weekdays),
                "highest_sales": round(max_value, 2),
                "is_highest": abs(current_value - max_value) < 0.005,
                "rank": rank,
            }

    out_items = [x for x in inventory.get("order_list", []) if x.get("status") == "out"]

    return {
        "combined_sales": combined_sales,
        "highest_sales_branch": highest_sales_branch,
        "highest_selling_item": highest_qty,
        "lowest_selling_item": lowest_qty,
        "highest_revenue_item": highest_revenue,
        "pizza_qty": usage["pizza_qty"],
        "cheese_used_kg": usage["cheese_used_kg"],
        "cheese_remaining_kg": round(cheese_remaining_total, 2) if cheese_remaining_known else None,
        "cheese_per_pizza_kg": usage["cheese_per_pizza_kg"],
        "branches": branch_summary,
        "order_list": inventory.get("order_list", []),
        "out_of_stock_order_list": out_items,
        "order_count": inventory.get("order_count", 0),
        "week_comparison": week_comparison,
        "weekday_comparison": weekday_comparison,
    }

def build_insights(sales, purchase, inventory, branches, management=None):
    """Return exactly eight owner-focused management highlights."""
    management = management or build_management(sales, inventory, branches)
    highlights = []

    # 1. Last 7 days versus the previous 7 days.
    week = management.get("week_comparison")
    if week and week.get("previous_sales"):
        change = week.get("change_pct") or 0
        direction = "higher" if change >= 0 else "lower"
        highlights.append({
            "key": "week",
            "tone": "positive" if change >= 0 else "warning",
            "text": (
                f"Last week's sales were NPR {week['current_sales']:,.0f}, "
                f"{abs(change):.1f}% {direction} than the previous week "
                f"(NPR {week['previous_sales']:,.0f})."
            ),
        })
    elif week:
        highlights.append({
            "key": "week",
            "tone": "neutral",
            "text": (
                f"Last week's sales were NPR {week['current_sales']:,.0f}. "
                "Previous-week data is not available for comparison."
            ),
        })
    else:
        highlights.append({
            "key": "week",
            "tone": "neutral",
            "text": "Weekly sales comparison is not available yet because there is not enough dated sales history.",
        })

    # 2. Compare the latest weekday with all occurrences of the same weekday in that month.
    weekday = management.get("weekday_comparison")
    if weekday and weekday.get("is_highest"):
        highlights.append({
            "key": "weekday",
            "tone": "success",
            "text": (
                f"This {weekday['weekday']} recorded the highest {weekday['weekday']} sales "
                f"of the month at NPR {weekday['sales']:,.0f}."
            ),
        })
    elif weekday:
        rank = weekday.get("rank")
        rank_text = f"ranked #{rank}" if rank else "was recorded"
        highlights.append({
            "key": "weekday",
            "tone": "neutral",
            "text": (
                f"This {weekday['weekday']} {rank_text} among {weekday['count']} "
                f"{weekday['weekday']}s this month, with sales of NPR {weekday['sales']:,.0f}."
            ),
        })
    else:
        highlights.append({
            "key": "weekday",
            "tone": "neutral",
            "text": "Same-weekday monthly comparison is not available yet because there is not enough dated sales history.",
        })

    # 3. Total pizzas sold.
    highlights.append({
        "key": "pizza",
        "tone": "neutral",
        "text": f"Total pizzas sold: {management.get('pizza_qty', 0):,.0f} across the selected branches.",
    })

    # 4. Only out-of-stock items are treated as urgent order alerts.
    out_items = management.get("out_of_stock_order_list", [])
    if out_items:
        s = settings_dict()
        details = []
        for item in out_items:
            branch_name = s.get(f"branch_{item['branch_id']}_name", f"Branch {item['branch_id']}")
            unit = item.get("unit") or "unit"
            details.append(
                f"{item['item']} at {branch_name} — order {number(item.get('order_qty')):,.2f} {unit}"
            )
        highlights.append({
            "key": "stock",
            "tone": "danger",
            "text": "Out-of-stock items that should be ordered:",
            "items": details,
        })
    else:
        highlights.append({
            "key": "stock",
            "tone": "success",
            "text": "No inventory items are currently marked out of stock.",
        })

    # 5. Combined sales.
    branch_count = len(management.get("branches", []))
    highlights.append({
        "key": "sales",
        "tone": "neutral",
        "text": (
            f"Total sales of both branches: NPR {management.get('combined_sales', 0):,.0f}."
            if branch_count == 2
            else f"Total sales for the selected branch: NPR {management.get('combined_sales', 0):,.0f}."
        ),
    })

    # 6. Highest-sales outlet.
    top_outlet = management.get("highest_sales_branch")
    highlights.append({
        "key": "outlet",
        "tone": "neutral",
        "text": (
            f"Highest-sales outlet: {top_outlet['branch_name']} with sales of NPR {number(top_outlet.get('sales')):,.0f}."
            if top_outlet and number(top_outlet.get("sales")) > 0
            else "Highest-sales outlet: no branch sales data is available for the selected period."
        ),
    })

    # 7. Best-selling item.
    best = management.get("highest_selling_item")
    highlights.append({
        "key": "best",
        "tone": "neutral",
        "text": (
            f"Best-selling item: {best['name']} with {number(best.get('qty')):,.0f} sold."
            if best
            else "Best-selling item: no sold-item data is available."
        ),
    })

    # 8. Cheese usage and remaining inventory.
    remaining = management.get("cheese_remaining_kg")
    remaining_text = (
        f"{remaining:,.2f} kg remaining in current inventory"
        if remaining is not None
        else "remaining cheese stock is not available"
    )
    highlights.append({
        "key": "cheese",
        "tone": "danger",
        "text": (
            f"Cheese consumed: {management.get('cheese_used_kg', 0):,.2f} kg; "
            f"{remaining_text}."
        ),
    })

    return highlights[:8]



def build_owner_welcome():
    """Return the previous local business-date snapshot across both branches."""
    snapshot_date_obj = datetime.now(APP_TIMEZONE).date() - timedelta(days=1)
    snapshot_date = snapshot_date_obj.isoformat()
    snapshot_ups = fetch_uploads([1, 2], snapshot_date, snapshot_date)
    sales = summarize_sales(
        [u for u in snapshot_ups if u["file_type"] == "sales"],
        [u for u in snapshot_ups if u["file_type"] == "sold_items"],
    )
    usage = calculate_ingredient_usage(sales)

    dishes = [x for x in sales.get("dishes", []) if number(x.get("qty")) > 0]
    best = max(
        dishes,
        key=lambda x: (number(x.get("qty")), number(x.get("sales"))),
    ) if dishes else None

    s = settings_dict()
    return {
        "date": snapshot_date,
        "date_label": snapshot_date_obj.strftime("%A, %d %B %Y"),
        "restaurant_name": s.get("restaurant_name", "Restaurant"),
        "pizza_qty": round(number(usage.get("pizza_qty")), 2),
        "total_sales": round(number(sales.get("total")), 2),
        "highest_sold_item": best,
        "bills": int(number(sales.get("bills"))),
        "tickets": int(number(sales.get("tickets", sales.get("bills")))),
        "has_data": bool(snapshot_ups),
    }



class LoginBody(BaseModel):
    username: str
    password: str


APP_ASSET_VERSION = "9.7"


@app.middleware("http")
async def disable_ui_cache(request: Request, call_next):
    response = await call_next(request)
    # Avoid stale dashboard JavaScript after GitHub/Railway redeploys.
    if request.url.path in ("/", "/static/app.js", "/static/styles.css"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/", response_class=HTMLResponse)
def home():
    html = (BASE / "templates" / "index.html").read_text(encoding="utf-8")
    # Existing templates may still reference an older ?v=6 asset. Replace it
    # dynamically so users always receive the current JavaScript after deploy.
    html = re.sub(
        r'/static/styles\.css(?:\?v=[^"\']+)?',
        f'/static/styles.css?v={APP_ASSET_VERSION}',
        html,
    )
    html = re.sub(
        r'/static/app\.js(?:\?v=[^"\']+)?',
        f'/static/app.js?v={APP_ASSET_VERSION}',
        html,
    )
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/sold-items-template.xlsx")
def sold_items_template():
    path = SAMPLE_DIR / "Sold-Items-Sample.xlsx"
    return FileResponse(path, filename="Sold-Items-Template.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/inventory-template.xlsx")
def inventory_template():
    path = SAMPLE_DIR / "Inventory-Sample.xlsx"
    return FileResponse(path, filename="Inventory-Template.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/login")
def login(body: LoginBody):
    with db() as conn:
        row=conn.execute("SELECT * FROM users WHERE username=?",(body.username.strip(),)).fetchone()
    if not row or not row["active"] or not verify_password(body.password,row["password_hash"]):
        raise HTTPException(401,"Invalid username or password.")
    token=sign_session(row["id"])
    response=JSONResponse({"ok":True})
    response.set_cookie("restaurant_session",token,httponly=True,samesite="strict",max_age=43200)
    return response


@app.post("/api/logout")
def logout():
    response=JSONResponse({"ok":True}); response.delete_cookie("restaurant_session"); return response


@app.get("/api/me")
def me(request:Request):
    user=current_user(request); s=settings_dict()
    return {"user":user,"settings":s}


@app.get("/api/owner-welcome")
def owner_welcome(request: Request):
    user = current_user(request)
    if user["role"] != "owner":
        raise HTTPException(403, "Owner only.")
    return build_owner_welcome()


@app.get("/api/dashboard")
def dashboard(request:Request, branch:str="all", start:Optional[str]=None, end:Optional[str]=None):
    user=current_user(request)
    if user["role"]!="owner":
        branch_ids=[user["branch_id"]]
    elif branch=="all":
        branch_ids=[1,2]
    else:
        bid=int(branch)
        if bid not in (1,2):
            raise HTTPException(400,"Invalid branch.")
        branch_ids=[bid]

    ups=fetch_uploads(branch_ids,start,end)
    sales=summarize_sales(
        [u for u in ups if u["file_type"]=="sales"],
        [u for u in ups if u["file_type"]=="sold_items"],
    )
    purchase=summarize_purchase([u for u in ups if u["file_type"]=="purchase"])
    daybook=summarize_daybook([u for u in ups if u["file_type"]=="daybook"])
    inventory=inventory_from_uploads(ups,branch_ids)

    branches=[branch_metrics(b,start,end) for b in branch_ids]
    if user["role"]=="owner" and branch=="all":
        branches=[branch_metrics(1,start,end),branch_metrics(2,start,end)]

    management=build_management(sales,inventory,branches)
    s=settings_dict()
    recent=[{
        "id":u["id"],
        "branch_id":u["branch_id"],
        "branch_name":s[f"branch_{u['branch_id']}_name"],
        "date":u["upload_date"],
        "type":u["file_type"],
        "name":u["original_name"],
        "uploaded_at":u["uploaded_at"],
        "source":"excel",
    } for u in ups]
    recent=sorted(recent,key=lambda x:x["uploaded_at"],reverse=True)[:12]
    return {
        "sales":sales,
        "purchase":purchase,
        "daybook":daybook,
        "inventory":inventory,
        "branches":branches,
        "management":management,
        "insights":build_insights(sales,purchase,inventory,branches,management),
        "recent_uploads":recent,
        "settings":s,
    }


@app.post("/api/upload")
async def upload(request:Request, branch_id:int=Form(...), upload_date:str=Form(...), file_type:str=Form(...), file:UploadFile=File(...)):
    user=current_user(request)
    if branch_id not in (1,2) or not can_access_branch(user,branch_id): raise HTTPException(403,"You cannot upload for this branch.")
    if file_type not in ("purchase","daybook","sales","sold_items","inventory"): raise HTTPException(400,"Invalid file type.")
    ext=Path(file.filename or "").suffix.lower()
    if ext not in (".xlsx",".xlsm"): raise HTTPException(400,"Please upload an .xlsx or .xlsm file.")
    content=await file.read()
    if len(content)>15*1024*1024: raise HTTPException(400,"File is larger than 15 MB.")
    try:
        sheet_name, headers, rows=parse_upload_bytes(content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400,f"Could not read workbook: {e}")
    if not headers:
        raise HTTPException(400,"Workbook has no readable table.")
    # Critical: validate the selected file type BEFORE writing the file or touching SQLite.
    validate_upload_structure(file_type, headers, rows)
    safe=re.sub(r"[^A-Za-z0-9._-]+","_",Path(file.filename).name)
    target_dir=UPLOAD_DIR/str(branch_id)/upload_date; target_dir.mkdir(parents=True,exist_ok=True)
    path=target_dir/f"{file_type}_{safe}"; path.write_bytes(content)
    now=datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        existing=conn.execute("SELECT id,stored_path FROM uploads WHERE branch_id=? AND upload_date=? AND file_type=?",(branch_id,upload_date,file_type)).fetchone()
        if existing:
            conn.execute("UPDATE uploads SET original_name=?,stored_path=?,sheet_name=?,headers_json=?,rows_json=?,uploaded_by=?,uploaded_at=? WHERE id=?",
                (file.filename,str(path),sheet_name,json.dumps(headers),json.dumps(rows),user["id"],now,existing["id"]))
            upload_id=existing["id"]
        else:
            cur=conn.execute("INSERT INTO uploads(branch_id,upload_date,file_type,original_name,stored_path,sheet_name,headers_json,rows_json,uploaded_by,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (branch_id,upload_date,file_type,file.filename,str(path),sheet_name,json.dumps(headers),json.dumps(rows),user["id"],now))
            upload_id=cur.lastrowid
    return {"ok":True,"id":upload_id,"sheet":sheet_name,"rows":len(rows),"columns":headers}


@app.get("/api/uploads")
def uploads(request:Request, branch:str="all"):
    user=current_user(request)
    if user["role"]=="owner": branch_ids=[1,2] if branch=="all" else [int(branch)]
    else: branch_ids=[user["branch_id"]]
    s=settings_dict(); ups=fetch_uploads(branch_ids)
    rows=[{"id":u["id"],"branch_id":u["branch_id"],"branch_name":s[f"branch_{u['branch_id']}_name"],"date":u["upload_date"],"type":u["file_type"],"name":u["original_name"],"sheet":u["sheet_name"],"rows":len(u["rows"]),"uploaded_at":u["uploaded_at"],"source":"excel"} for u in ups]
    return sorted(rows,key=lambda x:(x["date"],x["uploaded_at"]),reverse=True)


@app.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id:int, request:Request):
    user=current_user(request)
    with db() as conn:
        row=conn.execute("SELECT * FROM uploads WHERE id=?",(upload_id,)).fetchone()
        if not row: raise HTTPException(404,"Upload not found.")
        if not can_access_branch(user,row["branch_id"]): raise HTTPException(403,"Not allowed.")
        conn.execute("DELETE FROM uploads WHERE id=?",(upload_id,))
    try:
        if row["stored_path"]: Path(row["stored_path"]).unlink(missing_ok=True)
    except Exception: pass
    return {"ok":True}


@app.post("/api/load-samples")
def load_samples(request:Request):
    user=current_user(request)
    if user["role"]!="owner": raise HTTPException(403,"Owner only.")
    samples=[("purchase","2026-08-06","Purchase-Expense-Sample.xlsx"),("daybook","2026-07-19","Daybook-Sample.xlsx"),("sales","2026-08-07","Sales-Sample.xlsx"),("sold_items","2026-08-07","Sold-Items-Sample.xlsx"),("inventory","2026-08-07","Inventory-Sample.xlsx")]
    loaded=[]
    for typ,date,name in samples:
        p=SAMPLE_DIR/name; content=p.read_bytes(); sheet,headers,rows=parse_upload_bytes(content)
        target=UPLOAD_DIR/"1"/date; target.mkdir(parents=True,exist_ok=True); stored=target/f"{typ}_{name}"; shutil.copy2(p,stored)
        with db() as conn:
            existing=conn.execute("SELECT id FROM uploads WHERE branch_id=1 AND upload_date=? AND file_type=?",(date,typ)).fetchone()
            values=(name,str(stored),sheet,json.dumps(headers),json.dumps(rows),user["id"],datetime.now().isoformat(timespec="seconds"))
            if existing:
                conn.execute("UPDATE uploads SET original_name=?,stored_path=?,sheet_name=?,headers_json=?,rows_json=?,uploaded_by=?,uploaded_at=? WHERE id=?",values+(existing["id"],))
            else:
                conn.execute("INSERT INTO uploads(branch_id,upload_date,file_type,original_name,stored_path,sheet_name,headers_json,rows_json,uploaded_by,uploaded_at) VALUES(1,?,?,?,?,?,?,?,?,?)",(date,typ)+values)
        loaded.append({"type":typ,"rows":len(rows)})
    return {"ok":True,"loaded":loaded}


@app.get("/api/users")
def list_users(request:Request):
    user=current_user(request)
    if user["role"]!="owner": raise HTTPException(403,"Owner only.")
    with db() as conn:
        rows=conn.execute("SELECT id,username,display_name,role,branch_id,active,created_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


class NewUser(BaseModel):
    username:str; display_name:str; password:str; role:str; branch_id:Optional[int]=None


@app.post("/api/users")
def add_user(body:NewUser, request:Request):
    user=current_user(request)
    if user["role"]!="owner": raise HTTPException(403,"Owner only.")
    if body.role not in ("owner","manager","head_employee"): raise HTTPException(400,"Invalid role.")
    branch=None if body.role=="owner" else body.branch_id
    if body.role!="owner" and branch not in (1,2): raise HTTPException(400,"Select a branch.")
    if len(body.password)<6: raise HTTPException(400,"Password must be at least 6 characters.")
    try:
        with db() as conn:
            conn.execute("INSERT INTO users(username,display_name,password_hash,role,branch_id,active,created_at) VALUES(?,?,?,?,?,1,?)",
                (body.username.strip(),body.display_name.strip(),hash_password(body.password),body.role,branch,datetime.now().isoformat(timespec="seconds")))
    except sqlite3.IntegrityError:
        raise HTTPException(400,"Username already exists.")
    return {"ok":True}


@app.post("/api/users/{user_id}/toggle")
def toggle_user(user_id:int, request:Request):
    user=current_user(request)
    if user["role"]!="owner": raise HTTPException(403,"Owner only.")
    if user_id==user["id"]: raise HTTPException(400,"You cannot disable your own account.")
    with db() as conn:
        row=conn.execute("SELECT active FROM users WHERE id=?",(user_id,)).fetchone()
        if not row: raise HTTPException(404,"User not found.")
        conn.execute("UPDATE users SET active=? WHERE id=?",(0 if row["active"] else 1,user_id))
    return {"ok":True}


class SettingsBody(BaseModel):
    restaurant_name:str; branch_1_name:str; branch_2_name:str


@app.post("/api/settings")
def save_settings(body:SettingsBody, request:Request):
    user=current_user(request)
    if user["role"]!="owner": raise HTTPException(403,"Owner only.")
    with db() as conn:
        for k,v in body.model_dump().items(): conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v.strip()))
    return {"ok":True}


class ThresholdBody(BaseModel):
    branch_id:int; item_name:str; minimum_qty:float; unit:str=""


@app.post("/api/stock-thresholds")
def save_threshold(body:ThresholdBody, request:Request):
    user=current_user(request)
    if not can_access_branch(user,body.branch_id): raise HTTPException(403,"Not allowed.")
    with db() as conn:
        conn.execute("INSERT INTO stock_thresholds(branch_id,item_name,minimum_qty,unit) VALUES(?,?,?,?) ON CONFLICT(branch_id,item_name) DO UPDATE SET minimum_qty=excluded.minimum_qty, unit=excluded.unit",
            (body.branch_id,body.item_name.strip(),body.minimum_qty,body.unit.strip()))
    return {"ok":True}


@app.get("/health")
def health(): return {"ok":True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=False)
