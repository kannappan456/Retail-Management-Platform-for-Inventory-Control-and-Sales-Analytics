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
        for table in ["transactions", "users"]:
            print(f"\n--- {table.upper()} TABLE ---")
            cursor.execute(f"DESCRIBE `{table}`")

            for column in cursor.fetchall():
                print(column)

finally:
    connection.close()