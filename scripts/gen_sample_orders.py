"""Generate a synthetic Order History.csv for screenshots / demos.

The file matches Amazon's column schema but contains entirely fabricated data.
Run: python3 scripts/gen_sample_orders.py <output_path>
"""
import csv
import random
import sys
from datetime import datetime, timedelta

random.seed(42)

# (product name, price range, category bucket hint)
CATALOG = [
    ("Sparkling water 500ml x12 pack", (1800, 2800), "Groceries"),
    ("Premium Tea Variety Box", (1200, 3500), "Groceries"),
    ("Instant Coffee 200g", (800, 1800), "Groceries"),
    ("Specialty Food Hamper", (3000, 9000), "Groceries"),
    ("USB-C to USB-C Cable 1m", (700, 1900), "Electronics"),
    ("Wireless Mouse Ergonomic", (1500, 5000), "Electronics"),
    ("Mechanical Keyboard 60%", (6000, 18000), "Electronics"),
    ("Bluetooth Earbuds Noise Cancelling", (3000, 25000), "Electronics"),
    ("iPhone Charging Cable Braided", (900, 2500), "Electronics"),
    ("Mini PC Barebone Kit", (35000, 85000), "Electronics"),
    ("Portable Battery 20000mAh", (2500, 6500), "Electronics"),
    ("Kindle Paperwhite Reader", (15000, 22000), "Books"),
    ("Kindle Magazine Subscription", (400, 1200), "Books"),
    ("Programming Book Hardcover", (3000, 7000), "Books"),
    ("Novel Special Edition", (1500, 4000), "Books"),
    ("Cotton T-shirt Plain", (1500, 3500), "Clothing"),
    ("Running Shoes Lightweight", (5000, 14000), "Clothing"),
    ("Denim Shirt Casual", (2500, 6500), "Clothing"),
    ("Travel Backpack 30L", (4000, 12000), "Clothing"),
    ("Hand Soap Refill 1L", (500, 1400), "Health & Beauty"),
    ("Shampoo Salon Quality", (1200, 3500), "Health & Beauty"),
    ("Beauty Skincare Set", (2500, 9500), "Health & Beauty"),
    ("Laundry Detergent Concentrate", (700, 1900), "Health & Beauty"),
    ("Yoga Mat Non-slip", (2000, 5500), "Other"),
    ("Cast Iron Skillet 26cm", (4000, 9000), "Other"),
    ("Smart LED Bulb 4-pack", (2000, 5000), "Other"),
    ("Robot Vacuum Entry Model", (25000, 55000), "Other"),
    ("Office Chair Ergonomic", (15000, 45000), "Other"),
    ("Standing Desk Adjustable", (28000, 75000), "Other"),
]

CANCEL_RATE = 0.05
ORDERS_PER_YEAR = {
    2017: 12, 2018: 18, 2019: 22, 2020: 28, 2021: 35,
    2022: 30, 2023: 26, 2024: 24, 2025: 22, 2026: 8,
}

COLUMNS = [
    "ASIN", "Billing Address", "Carrier Name & Tracking Number", "Currency",
    "Gift Message", "Gift Recipient Contact", "Gift Sender Name",
    "Item Serial Number", "Order Date", "Order ID", "Order Status",
    "Original Quantity", "Payment Method Type", "Product Condition",
    "Product Name", "Purchase Order Number", "Ship Date",
    "Shipment Item Subtotal", "Shipment Item Subtotal Tax", "Shipment Status",
    "Shipping Address", "Shipping Charge", "Shipping Option", "Total Amount",
    "Total Discounts", "Unit Price", "Unit Price Tax", "Website",
]


def random_date_in_year(year: int) -> datetime:
    start = datetime(year, 1, 1)
    end_doy = 365 if year < 2026 else 100  # 2026 partial
    return start + timedelta(days=random.randint(0, end_doy - 1),
                             hours=random.randint(0, 23),
                             minutes=random.randint(0, 59))


def jpy(n: int) -> str:
    return f"{n:,}"


def main(out_path: str) -> None:
    rows = []
    for year, count in ORDERS_PER_YEAR.items():
        for _ in range(count):
            name, (lo, hi), _cat = random.choice(CATALOG)
            unit_price = random.randint(lo, hi)
            tax = round(unit_price * 0.10)
            total = unit_price + tax
            order_date = random_date_in_year(year)
            cancelled = random.random() < CANCEL_RATE
            row = {c: "Not Available" for c in COLUMNS}
            row.update({
                "ASIN": f"B0{random.randint(10**8, 10**9 - 1)}",
                "Currency": "JPY",
                "Order Date": order_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Order ID": f"250-{random.randint(1000000, 9999999)}-{random.randint(1000000, 9999999)}",
                "Order Status": "Cancelled" if cancelled else "Closed",
                "Original Quantity": "1",
                "Payment Method Type": "Credit Card - 0000",
                "Product Condition": "New",
                "Product Name": name,
                "Ship Date": order_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Shipment Item Subtotal": jpy(unit_price),
                "Shipment Item Subtotal Tax": jpy(tax),
                "Shipment Status": "Shipped",
                "Shipping Charge": "0",
                "Shipping Option": "standard",
                "Total Amount": jpy(0 if cancelled else total),
                "Total Discounts": "0",
                "Unit Price": jpy(unit_price),
                "Unit Price Tax": jpy(tax),
                "Website": "Amazon.example",
            })
            rows.append(row)

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_NONNUMERIC)
        w.writeheader()
        w.writerows(rows)

    closed_total = sum(int(r["Total Amount"].replace(",", "")) for r in rows if r["Order Status"] == "Closed")
    print(f"Wrote {len(rows)} rows to {out_path}")
    print(f"Closed total: ¥{closed_total:,}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Order History.csv")
