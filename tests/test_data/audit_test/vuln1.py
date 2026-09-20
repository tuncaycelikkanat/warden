import sqlite3

def vulnerable_sql(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    conn = sqlite3.connect("users.db")
    conn.execute(query)
    return query

