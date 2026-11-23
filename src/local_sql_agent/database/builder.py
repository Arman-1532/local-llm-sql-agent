"""Database builder module.
Populates SQLite database from fixed random seed and schema.sql.
"""

import os
import random
import sqlite3
from typing import Optional

from local_sql_agent.database.connection import DEFAULT_DB_PATH, get_write_connection

DEFAULT_SEED = 42

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema.sql")

FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona", "George", "Hannah",
    "Ian", "Julia", "Kevin", "Luna", "Michael", "Nora", "Oliver", "Paula",
    "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xander", "Yara", "Zack"
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson"
]
CITIES = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Seattle", "Austin", "Boston", "Denver", "Atlanta"]

PRODUCT_DATA = [
    ("Wireless Mouse", "Electronics", 29.99),
    ("Mechanical Keyboard", "Electronics", 89.99),
    ("USB-C Hub", "Electronics", 34.50),
    ("27-inch Monitor", "Electronics", 249.99),
    ("Noise-Cancelling Headphones", "Electronics", 129.00),
    ("Webcam 1080p", "Electronics", 49.99),
    ("Bluetooth Speaker", "Electronics", 39.95),
    ("Cotton T-Shirt", "Clothing", 19.99),
    ("Denim Jeans", "Clothing", 49.50),
    ("Hooded Sweatshirt", "Clothing", 39.99),
    ("Wool Winter Beanie", "Clothing", 14.99),
    ("Running Shoes", "Clothing", 79.99),
    ("Leather Belt", "Clothing", 24.50),
    ("Clean Architecture Book", "Books", 35.00),
    ("Designing Data-Intensive Apps", "Books", 45.00),
    ("Python Cookbook", "Books", 42.50),
    ("AI Agents Handbook", "Books", 49.99),
    ("The Pragmatic Programmer", "Books", 38.00),
    ("Ceramic Coffee Mug", "Home", 12.50),
    ("Stainless Steel Water Bottle", "Home", 18.99),
    ("Desk Lamp LED", "Home", 27.99),
    ("Ergonomic Cushion", "Home", 32.00),
    ("Scented Candle", "Home", 15.00),
    ("Kitchen Chef Knife", "Home", 55.00),
    ("Silicone Cooking Utensils", "Home", 22.90),
]


def build_database(db_path: Optional[str] = None, seed: int = DEFAULT_SEED) -> str:
    """Builds and populates the database deterministically from fixed random seed."""
    target_path = os.path.abspath(db_path or DEFAULT_DB_PATH)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    if os.path.exists(target_path):
        os.remove(target_path)

    rng = random.Random(seed)

    # Read schema.sql
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_write_connection(target_path)
    cur = conn.cursor()
    cur.executescript(schema_sql)

    # 1. Populate customers (50 rows)
    customers = []
    for cid in range(1, 51):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{cid}@example.com"
        city = rng.choice(CITIES)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        signup_date = f"2025-{month:02d}-{day:02d}"
        customers.append((cid, name, email, city, signup_date))

    cur.executemany(
        "INSERT INTO customers (customer_id, name, email, city, signup_date) VALUES (?, ?, ?, ?, ?)",
        customers
    )

    # 2. Populate products (25 rows)
    products = []
    for pid, (pname, cat, price) in enumerate(PRODUCT_DATA, start=1):
        stock = rng.randint(10, 200)
        products.append((pid, pname, cat, price, stock))

    cur.executemany(
        "INSERT INTO products (product_id, name, category, price, stock_quantity) VALUES (?, ?, ?, ?, ?)",
        products
    )

    # 3. Populate orders (120 rows)
    orders = []
    statuses = ["completed", "completed", "completed", "pending", "cancelled"]
    for oid in range(1, 121):
        cid = rng.randint(1, 50)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        order_date = f"2025-{month:02d}-{day:02d}"
        status = rng.choice(statuses)
        orders.append((oid, cid, order_date, status))

    cur.executemany(
        "INSERT INTO orders (order_id, customer_id, order_date, status) VALUES (?, ?, ?, ?)",
        orders
    )

    # 4. Populate order_items (300 rows, ensuring >100 rows requirement)
    order_items = []
    item_id = 1
    for oid in range(1, 121):
        count = rng.randint(1, 4)
        for prod in rng.sample(products, count):
            pid, _, _, unit_price, _ = prod
            qty = rng.randint(1, 5)
            order_items.append((item_id, oid, pid, qty, unit_price))
            item_id += 1

    while len(order_items) < 300:
        oid = rng.randint(1, 120)
        prod = rng.choice(products)
        pid, _, _, unit_price, _ = prod
        qty = rng.randint(1, 3)
        order_items.append((item_id, oid, pid, qty, unit_price))
        item_id += 1

    cur.executemany(
        "INSERT INTO order_items (item_id, order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
        order_items
    )

    conn.commit()
    conn.close()
    return target_path


if __name__ == "__main__":
    p = build_database()
    print(f"Database successfully generated at: {p}")
