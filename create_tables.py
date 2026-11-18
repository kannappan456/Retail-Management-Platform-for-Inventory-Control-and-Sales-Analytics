import os
import re
import pymysql

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "shopsense")

if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
    raise ValueError(
        "DB_NAME can contain only letters, numbers, and underscores."
    )

# Create the database if it doesn't exist.
connection = pymysql.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    autocommit=True
)

try:
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"
        )
    print(f"Database '{DB_NAME}' is ready.")
finally:
    connection.close()

database_url = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME
)

engine = create_engine(
    database_url,
    pool_pre_ping=True
)

statements = [
    """
    CREATE TABLE IF NOT EXISTS vendors (
        vendor_id INT AUTO_INCREMENT PRIMARY KEY,
        business_name VARCHAR(100) NOT NULL,
        owner_name VARCHAR(100) NOT NULL,
        email VARCHAR(150) NOT NULL UNIQUE,
        phone VARCHAR(20),
        category VARCHAR(100),
        status ENUM('Pending', 'Active', 'Suspended')
            NOT NULL DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS products (
        product_id INT AUTO_INCREMENT PRIMARY KEY,
        vendor_id INT NOT NULL,
        product_name VARCHAR(150) NOT NULL,
        category VARCHAR(100),
        price DECIMAL(10, 2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vendor_id)
            REFERENCES vendors(vendor_id),
        CHECK (price >= 0)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS inventory (
        inventory_id INT AUTO_INCREMENT PRIMARY KEY,
        product_id INT NOT NULL UNIQUE,
        current_stock INT NOT NULL DEFAULT 0,
        warehouse VARCHAR(100),
        reorder_level INT NOT NULL DEFAULT 10,
        FOREIGN KEY (product_id)
            REFERENCES products(product_id),
        CHECK (current_stock >= 0),
        CHECK (reorder_level >= 0)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INT AUTO_INCREMENT PRIMARY KEY,
        product_id INT NOT NULL,
        vendor_id INT NOT NULL,
        quantity INT NOT NULL,
        amount DECIMAL(12, 2) NOT NULL,
        transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status ENUM('Completed', 'Cancelled', 'Refunded')
            NOT NULL DEFAULT 'Completed',
        FOREIGN KEY (product_id)
            REFERENCES products(product_id),
        FOREIGN KEY (vendor_id)
            REFERENCES vendors(vendor_id),
        CHECK (quantity > 0),
        CHECK (amount >= 0)
    )
    """,

    # NEW: User accounts for authentication.
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(150) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('Customer', 'Vendor', 'Admin')
            NOT NULL DEFAULT 'Customer',
        vendor_id INT UNIQUE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vendor_id)
            REFERENCES vendors(vendor_id)
    )
    """
]

try:
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

        result = connection.execute(text("SHOW TABLES"))
        tables = [row[0] for row in result]

    print("\nShopSense database setup complete!")
    print("Tables created or already present:")

    for table in tables:
        print("-", table)

finally:
    engine.dispose()