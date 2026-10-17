"""Dummy SQL sample file for AST and security scanner tests."""


def get_user(user_id):
    """Retrieve user query string unsafely."""
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query


# trigger scan
