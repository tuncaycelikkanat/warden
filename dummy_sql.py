def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query
# trigger scan
