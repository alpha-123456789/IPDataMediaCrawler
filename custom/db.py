from pathlib import Path
from dotenv import load_dotenv
import os
import pymysql

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def get_conn():
    return pymysql.connect(
        host=os.getenv("MYSQL_DB_HOST"),
        port=int(os.getenv("MYSQL_DB_PORT", "3306")),
        user=os.getenv("MYSQL_DB_USER"),
        password=os.getenv("MYSQL_DB_PWD"),
        database=os.getenv("MYSQL_DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
