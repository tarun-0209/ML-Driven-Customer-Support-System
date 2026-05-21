import sqlite3
DATABASE_URL = "reputation.db"

def get_db():
    # connecting to the database.
    connection = sqlite3.connect(DATABASE_URL, check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON;")

    #return rows as disctionaries instead of tuples for easier JSON conversions.
    connection.row_factory = sqlite3.Row

    try:
        yield connection
    finally:
        connection.close()
