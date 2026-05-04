import sqlite3
import os

db_path = r"c:\Users\Maxim\PycharmProjects\ezolimp\olimpiada.db"
if not os.path.exists(db_path):
    print("Database not found")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables: {tables}")
        for table in tables:
            tname = table[0]
            cursor.execute(f"PRAGMA table_info({tname});")
            info = cursor.fetchall()
            print(f"Table {tname} info: {info}")
        cursor.execute("SELECT COUNT(*) FROM tasks;")
        print(f"Tasks count: {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM task_views;")
        print(f"Task views count: {cursor.fetchone()[0]}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
