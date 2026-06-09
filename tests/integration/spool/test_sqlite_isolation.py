import sqlite3
import os
import sys


def test_one(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()


def test_two(tmp_path):
    db_path = tmp_path / "test2.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()
