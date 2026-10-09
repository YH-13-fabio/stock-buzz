"""SQLite 資料庫：存每則內容與「提到哪檔股票、看多還是看空」。"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, source TEXT, kind TEXT, url TEXT, title TEXT,
    author TEXT, published TEXT, date TEXT, fetched TEXT
);
CREATE TABLE IF NOT EXISTS mentions (
    item_id TEXT, code TEXT, sentiment INTEGER, date TEXT, source TEXT,
    PRIMARY KEY (item_id, code)
);
CREATE INDEX IF NOT EXISTS idx_mentions_date ON mentions(date);
"""


class DB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def save_item(self, item, fetched, kind=None, item_id=None, title=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?)",
            (item_id or item.id, item.source, kind or item.kind, item.url, title or item.title,
             item.author, item.published.isoformat(), item.date, fetched))

    def replace_mentions(self, item_id, date, source, sentiments):
        """同一則內容重新抓到時，先清掉舊判斷再寫新的（推文會隨時間增加）。"""
        self.conn.execute("DELETE FROM mentions WHERE item_id=? OR item_id LIKE ?",
                          (item_id, item_id + "#c%"))
        self.add_mentions(item_id, date, source, sentiments)

    def add_mentions(self, item_id, date, source, sentiments):
        self.conn.executemany(
            "INSERT OR REPLACE INTO mentions VALUES (?,?,?,?,?)",
            [(item_id, code, s, date, source) for code, s in sentiments.items()])

    def commit(self):
        self.conn.commit()
