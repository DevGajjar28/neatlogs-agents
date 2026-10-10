import sqlite3

from app.infra.db import TABLES, init_db


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "signalsdr.db"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()

    names = {row[0] for row in rows}
    assert set(TABLES) <= names
