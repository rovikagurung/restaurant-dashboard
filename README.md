# Restaurant Command Center — Excel Edition

A working two-branch restaurant dashboard with a clean white-and-red interface.

## Daily Excel workflow

For each branch and business date, upload any or all of these four reports:

1. **Purchase / Expense Excel**
2. **Daybook Excel**
3. **Sales Excel**
4. **Sold Items Excel**

The fourth file replaces the old food-sales photo/OCR workflow. **No Tesseract or photo reading is required.**

## Sold Items Excel format

The dashboard accepts common column-name variations, but the recommended format is:

| Rank | Dish Name | QTY | Amount | % of Sales |
|---|---|---:|---:|---:|
| 1 | Chicken Momo | 59 | 23305 | 31.07 |

Required for useful dish analysis:
- **Dish Name**
- **QTY**

Recommended:
- **Amount**

Optional:
- Rank
- % of Sales

The dashboard calculates the percentage contribution again for the selected date range, so the percentage column is optional.

A sample workbook is included at `sample-data/Sold-Items-Sample.xlsx` and can also be downloaded from the Daily Upload screen.

## What the dashboard shows

### Sales
- Total invoice sales
- Paid / unpaid sales
- Number of bills
- Average bill value
- Payment methods
- Order type / channel
- Billed-by employee performance
- Daily sales trend

### Sold items
- Total number of food/items sold
- Best seller by quantity
- Lowest seller by quantity
- Highest dish sales amount
- Dish-by-dish quantity
- Dish revenue
- Percentage contribution
- Branch-wise dish comparison

### Purchase / Expense
- Total purchase / expense
- Expense heads
- Payment accounts
- Daily trend
- Parsed expense lines

### Daybook
- Net Sales
- Total Receipts
- Expenses
- Total Payments
- Net Receipts
- Closing Balance
- Finance difference

### Inventory
Inventory alerts activate automatically when an uploaded Excel workbook contains item-level stock columns such as:
- Item Name / Ingredient / Stock Item
- Closing Stock / Available Qty / Current Stock
- optional Minimum Stock / Reorder Level
- optional Unit

## Login roles

### Owner / Admin
- Access both branches
- Upload for either branch
- View combined dashboard and branch comparison
- Add/disable users
- Rename the restaurant and branches
- Configure inventory minimum thresholds

### Manager / Head Employee
- Access only the assigned branch
- Upload all four daily Excel files for that branch
- View that branch's dashboard and history

## First-run accounts

- Owner: `owner` / `Owner@123`
- Branch 1 Manager: `manager1` / `Manager@123`
- Branch 2 Head Employee: `head2` / `Head@123`

Change/add staff users after logging in as Owner.

## Mac quick start

Open Terminal in the `restaurant_dashboard` folder and run:

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Or double-click `START_MAC.command`.

Then open:

`http://127.0.0.1:8000`

## Replacement rule

The unique upload key is:

**Branch + Business Date + File Type**

If the same report type is uploaded again for the same branch and date, the newer file replaces the older dataset instead of double-counting it.

Accepted formats: `.xlsx` and `.xlsm`.

## Data storage

- Database: `data/restaurant.db`
- Uploaded files: `data/uploads/`

Back up the entire `data` folder regularly.

## Upgrading from the earlier photo-OCR version

The app automatically upgrades the local database so it can store the new `sold_items` Excel type. You can keep your existing `data` folder when moving to this version.

The old photo OCR is no longer required by the dashboard.

## Online deployment

For public internet use, deploy behind HTTPS and use a production database/storage setup. Change all default passwords before public deployment.


## V5 interface
- White background
- Black text
- Hover/active accent: #d90819
- Removed instructional/demo panels and OCR wording from the interface
- Sold Items remains an Excel upload


## Dashboard graphs
The main dashboard includes Sales Trend, Sales vs Purchase/Expense, Top Selling Items, and Sales by Payment Mode graphs. Graphs update automatically from the selected branch/date filter.
