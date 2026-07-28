import os, sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = os.getenv("DATABASE_PATH", "data/monitor.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 site TEXT NOT NULL,
 url TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 price TEXT,
 image_url TEXT,
 first_seen TEXT NOT NULL,
 last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS variants (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 product_id INTEGER NOT NULL,
 color TEXT NOT NULL DEFAULT '',
 size TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL,
 last_checked TEXT NOT NULL,
 UNIQUE(product_id, color, size)
);
CREATE TABLE IF NOT EXISTS changes (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 product_id INTEGER NOT NULL,
 color TEXT NOT NULL DEFAULT '',
 size TEXT NOT NULL DEFAULT '',
 old_status TEXT NOT NULL,
 new_status TEXT NOT NULL,
 detected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 site TEXT NOT NULL,
 started_at TEXT NOT NULL,
 finished_at TEXT,
 status TEXT NOT NULL,
 product_count INTEGER DEFAULT 0,
 message TEXT
);
'''

@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
