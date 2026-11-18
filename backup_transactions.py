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

        cursor.execute("""
            SHOW TABLES LIKE 'transactions_backup_pre_customer_id'
        """)

        if cursor.fetchone():
            print("Backup already exists. No changes made.")
        else:
            cursor.execute("""
                CREATE TABLE transactions_backup_pre_customer_id
                LIKE transactions
            """)

            cursor.execute("""
                INSERT INTO transactions_backup_pre_customer_id
                SELECT * FROM transactions
            """)

            cursor.execute("""
                SELECT COUNT(*)
                FROM transactions_backup_pre_customer_id
            """)

            count = cursor.fetchone()[0]

            print("Backup created successfully!")
            print("Transactions backed up:", count)

finally:
    connection.close()