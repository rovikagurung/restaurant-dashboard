from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref or "A")
    if not letters:
        return 0
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _text(node):
    if node is None:
        return ""
    return "".join((t.text or "") for t in node.iter() if t.tag.endswith("}t"))


def _coerce_number(value: str):
    if value is None or value == "":
        return None
    try:
        n = float(value)
        if n.is_integer():
            return int(n)
        return n
    except Exception:
        return value


def read_xlsx_bytes(data: bytes) -> dict:
    """Read the first worksheet of an XLSX/XLSM file using Python stdlib only."""
    with zipfile.ZipFile(BytesIO(data)) as z:
        names = set(z.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError("This does not appear to be a valid .xlsx workbook.")

        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{{{NS_MAIN}}}si"):
                shared.append(_text(si))

        wb_root = ET.fromstring(z.read("xl/workbook.xml"))
        sheets_el = wb_root.find(f"{{{NS_MAIN}}}sheets")
        if sheets_el is None or len(sheets_el) == 0:
            return {"sheet_name": "Sheet1", "rows": []}

        first_sheet = sheets_el[0]
        sheet_name = first_sheet.attrib.get("name", "Sheet1")
        rid = first_sheet.attrib.get(f"{{{NS_REL}}}id")

        rel_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rel_root.findall(f"{{{NS_PKG_REL}}}Relationship"):
            if rel.attrib.get("Id") == rid:
                target = rel.attrib.get("Target")
                break
        if not target:
            raise ValueError("Could not resolve worksheet in workbook.")
        if target.startswith("/"):
            sheet_path = target.lstrip("/")
        elif target.startswith("xl/"):
            sheet_path = target
        else:
            sheet_path = "xl/" + target.lstrip("/")
        sheet_path = re.sub(r"/\./", "/", sheet_path)

        sheet_root = ET.fromstring(z.read(sheet_path))
        sheet_data = sheet_root.find(f"{{{NS_MAIN}}}sheetData")
        rows = []
        max_col = -1
        if sheet_data is not None:
            for row_el in sheet_data.findall(f"{{{NS_MAIN}}}row"):
                row_map = {}
                for c in row_el.findall(f"{{{NS_MAIN}}}c"):
                    ref = c.attrib.get("r", "A1")
                    idx = _col_index(ref)
                    max_col = max(max_col, idx)
                    ctype = c.attrib.get("t")
                    v = c.find(f"{{{NS_MAIN}}}v")
                    value = None
                    if ctype == "s":
                        if v is not None and v.text is not None:
                            try:
                                value = shared[int(v.text)]
                            except Exception:
                                value = v.text
                    elif ctype == "inlineStr":
                        is_el = c.find(f"{{{NS_MAIN}}}is")
                        value = _text(is_el)
                    elif ctype == "str":
                        value = v.text if v is not None else ""
                    elif ctype == "b":
                        value = bool(int(v.text)) if v is not None and v.text else False
                    else:
                        value = _coerce_number(v.text if v is not None else None)
                    row_map[idx] = value
                if row_map:
                    width = max(row_map.keys()) + 1
                    row = [None] * width
                    for idx, value in row_map.items():
                        row[idx] = value
                    rows.append(row)

        width = max_col + 1
        if width > 0:
            rows = [r + [None] * (width - len(r)) for r in rows]
        return {"sheet_name": sheet_name, "rows": rows}


def rows_to_dicts(rows):
    if not rows:
        return [], []
    headers = []
    seen = {}
    for i, h in enumerate(rows[0]):
        base = str(h).strip() if h not in (None, "") else f"Column {i+1}"
        key = base
        if key in seen:
            seen[key] += 1
            key = f"{base} ({seen[base]})"
        else:
            seen[key] = 1
        headers.append(key)
    data = []
    for row in rows[1:]:
        if not any(v not in (None, "") for v in row):
            continue
        data.append({headers[i]: row[i] if i < len(row) else None for i in range(len(headers))})
    return headers, data
