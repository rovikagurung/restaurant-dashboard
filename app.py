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
from datetime import datetime
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

app = FastAPI(title="Restaurant Command Center")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

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
                file_type TEXT NOT NULL CHECK(file_type IN ('purchase','daybook','sales','sold_items')),
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
        if upload_sql and "sold_items" not in (upload_sql["sql"] or ""):
            conn.executescript(
                """
                ALTER TABLE uploads RENAME TO uploads_legacy;
                CREATE TABLE uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    branch_id INTEGER NOT NULL,
                    upload_date TEXT NOT NULL,
                    file_type TEXT NOT NULL CHECK(file_type IN ('purchase','daybook','sales','sold_items')),
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
            "restaurant_name": "Restaurant Command Center",
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
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
        "bills": len(bills), "avg_bill": round(total / len(bills), 2) if bills else 0,
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
    total_k=find_key(headers,["Total","Total Amount","Net"])
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
        daily.append({
            "date":up["upload_date"],"branch_id":up["branch_id"],
            "net_sales":daybook_value(up,["NetSales","Net Sales"]),
            "receipts":daybook_value(up,["Total Receipts"]),
            "expenses":daybook_value(up,["Expenses"]),
            "payments":daybook_value(up,["Total Payments"]),
            "net_receipts":daybook_value(up,["Net Receipts"]),
            "closing_balance":daybook_value(up,["Closing Balance"]),
            "difference":daybook_value(up,["Difference"]),
        })
    if daily:
        latest_date=max(x["date"] for x in daily)
        latest_rows=[x for x in daily if x["date"]==latest_date]
        latest={"date":latest_date,"branch_id":latest_rows[0]["branch_id"] if len(latest_rows)==1 else None}
        for key in ("net_sales","receipts","expenses","payments","net_receipts","closing_balance","difference"):
            vals=[x[key] for x in latest_rows if x.get(key) is not None]
            latest[key]=sum(vals) if vals else None
    else:
        latest={}
    return {"daily":daily,"latest":latest}


def inventory_from_uploads(uploads, branch_ids):
    # Use the newest row-based stock file available for each selected branch.
    candidates=[]
    for branch_id in branch_ids:
        branch_candidates=[]
        branch_uploads=[u for u in uploads if u["branch_id"]==branch_id]
        for up in sorted(branch_uploads, key=lambda x:(x["upload_date"],x["id"]), reverse=True):
            h=up["headers"]
            item_k=find_key(h,["item name","stock item","ingredient","material","product","item"])
            stock_k=find_key(h,["closing stock","closing qty","available qty","stock qty","current stock","balance qty","stock"])
            min_k=find_key(h,["minimum qty","min stock","reorder level","reorder qty","minimum stock"])
            unit_k=find_key(h,["unit","uom"])
            if item_k and stock_k:
                for row in up["rows"]:
                    item=row.get(item_k)
                    if item in (None,"", "-"): continue
                    branch_candidates.append({"branch_id":up["branch_id"],"item":str(item).strip(),"qty":number(row.get(stock_k)),"minimum":number(row.get(min_k)) if min_k else None,"unit":str(row.get(unit_k) or "") if unit_k else "","date":up["upload_date"]})
                if branch_candidates: break
        candidates.extend(branch_candidates)
    # Merge user-set thresholds when the sheet itself lacks them.
    with db() as conn:
        th={ (r["branch_id"],r["item_name"].lower()):(r["minimum_qty"],r["unit"] or "") for r in conn.execute("SELECT * FROM stock_thresholds WHERE branch_id IN (%s)" % ",".join("?" for _ in branch_ids), branch_ids) }
    alerts=[]
    for r in candidates:
        if r["minimum"] is None:
            t=th.get((r["branch_id"],r["item"].lower()))
            if t: r["minimum"], r["unit"] = t[0], r["unit"] or t[1]
        if r["minimum"] is not None:
            if r["qty"] <= 0: status="out"
            elif r["qty"] <= r["minimum"]: status="low"
            else: status="ok"
        else: status="unknown"
        r["status"]=status
        alerts.append(r)
    alerts.sort(key=lambda x: (0 if x["status"]=="out" else 1 if x["status"]=="low" else 2, x["branch_id"], x["qty"]))
    return {"items":alerts,"has_stock_data":bool(candidates),"low_count":sum(1 for x in alerts if x["status"] in ("low","out")),"out_count":sum(1 for x in alerts if x["status"]=="out")}


def branch_metrics(branch_id, start=None, end=None):
    ups=fetch_uploads([branch_id],start,end)
    return {
        "branch_id":branch_id,
        "sales":summarize_sales([u for u in ups if u["file_type"]=="sales"], [u for u in ups if u["file_type"]=="sold_items"]),
        "purchase":summarize_purchase([u for u in ups if u["file_type"]=="purchase"]),
        "daybook":summarize_daybook([u for u in ups if u["file_type"]=="daybook"]),
    }


def build_insights(sales,purchase,inventory,branches):
    insights=[]
    if sales["total"]:
        insights.append(f"Total sales recorded: NPR {sales['total']:,.0f} from {sales['bills']} bills; average bill NPR {sales['avg_bill']:,.0f}.")
    if sales["unpaid"]:
        pct=sales["unpaid"]/sales["total"]*100 if sales["total"] else 0
        insights.append(f"Unpaid/due sales are NPR {sales['unpaid']:,.0f} ({pct:.1f}% of recorded sales).")
    if sales["payment_modes"]:
        top=sales["payment_modes"][0]
        insights.append(f"Top payment mode by value is {top['label']} at NPR {top['value']:,.0f}.")
    if purchase["heads"]:
        top=purchase["heads"][0]
        insights.append(f"Largest purchase/expense head is {top['label']} at NPR {top['value']:,.0f}.")
    if sales["dishes"]:
        insights.append(f"Best-selling dish by quantity is {sales['dishes'][0]['name']} ({sales['dishes'][0]['qty']:,.0f} units).")
        if len(sales["dishes"])>1:
            low=sales["dishes"][-1]; insights.append(f"Lowest-selling listed dish is {low['name']} ({low['qty']:,.0f} units).")
    if inventory["out_count"]: insights.append(f"{inventory['out_count']} inventory item(s) are out of stock.")
    elif inventory["low_count"]: insights.append(f"{inventory['low_count']} inventory item(s) are at/below minimum stock.")
    if len(branches)==2 and (branches[0]["sales"]["total"] or branches[1]["sales"]["total"]):
        lead=max(branches,key=lambda b:b["sales"]["total"]); other=min(branches,key=lambda b:b["sales"]["total"])
        diff=lead["sales"]["total"]-other["sales"]["total"]
        s=settings_dict(); name=s[f"branch_{lead['branch_id']}_name"]
        insights.append(f"{name} currently leads branch sales by NPR {diff:,.0f} in the selected period.")
    return insights[:7]


class LoginBody(BaseModel):
    username: str
    password: str


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/sold-items-template.xlsx")
def sold_items_template():
    path = SAMPLE_DIR / "Sold-Items-Sample.xlsx"
    return FileResponse(path, filename="Sold-Items-Template.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


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


@app.get("/api/dashboard")
def dashboard(request:Request, branch:str="all", start:Optional[str]=None, end:Optional[str]=None):
    user=current_user(request)
    if user["role"]!="owner": branch_ids=[user["branch_id"]]
    elif branch=="all": branch_ids=[1,2]
    else:
        bid=int(branch)
        if bid not in (1,2): raise HTTPException(400,"Invalid branch.")
        branch_ids=[bid]
    ups=fetch_uploads(branch_ids,start,end)
    sales=summarize_sales([u for u in ups if u["file_type"]=="sales"], [u for u in ups if u["file_type"]=="sold_items"])
    purchase=summarize_purchase([u for u in ups if u["file_type"]=="purchase"])
    daybook=summarize_daybook([u for u in ups if u["file_type"]=="daybook"])
    inventory=inventory_from_uploads(ups,branch_ids)
    branches=[branch_metrics(b,start,end) for b in branch_ids]
    # for owner all, ensure both branch comparison records even if no uploads
    if user["role"]=="owner" and branch=="all": branches=[branch_metrics(1,start,end),branch_metrics(2,start,end)]
    s=settings_dict()
    recent=[{"id":u["id"],"branch_id":u["branch_id"],"branch_name":s[f"branch_{u['branch_id']}_name"],"date":u["upload_date"],"type":u["file_type"],"name":u["original_name"],"uploaded_at":u["uploaded_at"],"source":"excel"} for u in ups]
    recent=sorted(recent,key=lambda x:x["uploaded_at"],reverse=True)[:12]
    return {"sales":sales,"purchase":purchase,"daybook":daybook,"inventory":inventory,"branches":branches,"insights":build_insights(sales,purchase,inventory,branches),"recent_uploads":recent,"settings":s}


@app.post("/api/upload")
async def upload(request:Request, branch_id:int=Form(...), upload_date:str=Form(...), file_type:str=Form(...), file:UploadFile=File(...)):
    user=current_user(request)
    if branch_id not in (1,2) or not can_access_branch(user,branch_id): raise HTTPException(403,"You cannot upload for this branch.")
    if file_type not in ("purchase","daybook","sales","sold_items"): raise HTTPException(400,"Invalid file type.")
    ext=Path(file.filename or "").suffix.lower()
    if ext not in (".xlsx",".xlsm"): raise HTTPException(400,"Please upload an .xlsx or .xlsm file.")
    content=await file.read()
    if len(content)>15*1024*1024: raise HTTPException(400,"File is larger than 15 MB.")
    try: sheet_name, headers, rows=parse_upload_bytes(content)
    except Exception as e: raise HTTPException(400,f"Could not read workbook: {e}")
    if not headers: raise HTTPException(400,"Workbook has no readable table.")
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
    samples=[("purchase","2026-08-06","Purchase-Expense-Sample.xlsx"),("daybook","2026-07-19","Daybook-Sample.xlsx"),("sales","2026-08-07","Sales-Sample.xlsx"),("sold_items","2026-08-07","Sold-Items-Sample.xlsx")]
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
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
