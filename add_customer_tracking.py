import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

connection = pymysql.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "shopsense"),
    autocommit=True
)

try:
    with connection.cursor() as cursor:

        cursor.execute("SHOW COLUMNS FROM transactions LIKE 'customer_id'")

        if cursor.fetchone():
            print("customer_id column already exists.")
        else:
            cursor.execute("""
                ALTER TABLE transactions
                ADD COLUMN customer_id INT NULL,
                ADD CONSTRAINT fk_transaction_customer
                FOREIGN KEY (customer_id)
                REFERENCES users(user_id)
                ON DELETE SET NULL
            """)

            print("customer_id column and foreign key added!")

        cursor.execute("DESCRIBE transactions")

        print("\nUpdated transactions table:")
        for column in cursor.fetchall():
            print(column)

finally:
    connection.close()