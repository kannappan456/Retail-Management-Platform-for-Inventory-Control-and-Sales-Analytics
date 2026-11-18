import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

connection = pymysql.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "shopsense")
)

try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                t.transaction_id,
                t.product_id,
                t.quantity,
                t.amount,
                t.customer_id,
                u.email
            FROM transactions t
            LEFT JOIN users u
                ON t.customer_id = u.user_id
            ORDER BY t.transaction_id DESC
            LIMIT 5
        """)

        rows = cursor.fetchall()

        print("\nLATEST TRANSACTIONS\n")

        for row in rows:
            print(row)

finally:
    connection.close()