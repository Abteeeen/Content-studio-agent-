"""Database layer — SQLite for tracking all outreach campaigns.

Tracks:
- Campaigns (city, date, status)
- Stores (deduplicated by place_id — never double-mail)
- Garments, reels, postcards per store
- QR scan analytics (who watched their reel)
- Email follow-up status
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from pipeline.config import OUTPUT_DIR

DB_PATH = os.path.join(os.path.dirname(OUTPUT_DIR), "outreach.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    radius INTEGER DEFAULT 5000,
    status TEXT DEFAULT 'running',
    stores_found INTEGER DEFAULT 0,
    stores_qualified INTEGER DEFAULT 0,
    reels_rendered INTEGER DEFAULT 0,
    postcards_mailed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT UNIQUE NOT NULL,
    campaign_id INTEGER REFERENCES campaigns(id),
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    website TEXT,
    rating REAL DEFAULT 0,
    review_count INTEGER DEFAULT 0,
    owner_name TEXT,
    score REAL DEFAULT 0,
    status TEXT DEFAULT 'discovered',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS garments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER REFERENCES stores(id),
    image_url TEXT,
    image_path TEXT,
    source TEXT,
    description TEXT,
    category TEXT,
    score REAL DEFAULT 0,
    is_selected BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER REFERENCES stores(id),
    garment_id INTEGER REFERENCES garments(id),
    video_path TEXT,
    video_url TEXT,
    thumbnail_path TEXT,
    watch_token TEXT UNIQUE,
    views INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS postcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER REFERENCES stores(id),
    reel_id INTEGER REFERENCES reels(id),
    front_path TEXT,
    back_path TEXT,
    qr_code_path TEXT,
    mail_service TEXT,
    tracking_id TEXT,
    mail_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mailed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reel_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reel_id INTEGER REFERENCES reels(id),
    store_id INTEGER REFERENCES stores(id),
    ip_address TEXT,
    user_agent TEXT,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER REFERENCES stores(id),
    email_address TEXT,
    subject TEXT,
    body TEXT,
    status TEXT DEFAULT 'pending',
    scheduled_for TIMESTAMP,
    sent_at TIMESTAMP,
    opened_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stores_place_id ON stores(place_id);
CREATE INDEX IF NOT EXISTS idx_reels_watch_token ON reels(watch_token);
CREATE INDEX IF NOT EXISTS idx_stores_status ON stores(status);
"""


def init_db() -> None:
    with get_db() as db:
        db.executescript(SCHEMA)


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def store_already_contacted(place_id: str) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM stores WHERE place_id = ? AND status IN ('mailed', 'reel_rendered', 'postcard_created')",
            (place_id,),
        ).fetchone()
        return row is not None


def create_campaign(city: str, radius: int) -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO campaigns (city, radius) VALUES (?, ?)",
            (city, radius),
        )
        return cur.lastrowid


def update_campaign(campaign_id: int, **kwargs) -> None:
    allowed = {"status", "stores_found", "stores_qualified", "reels_rendered", "postcards_mailed", "completed_at"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with get_db() as db:
        db.execute(
            f"UPDATE campaigns SET {set_clause} WHERE id = ?",
            (*fields.values(), campaign_id),
        )


def save_store(store_data: dict, campaign_id: int) -> int:
    with get_db() as db:
        cur = db.execute(
            """INSERT OR IGNORE INTO stores
               (place_id, campaign_id, name, address, phone, website, rating, review_count, owner_name, score, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                store_data["place_id"], campaign_id, store_data["name"],
                store_data.get("address", ""), store_data.get("phone", ""),
                store_data.get("website", ""), store_data.get("rating", 0),
                store_data.get("review_count", 0), store_data.get("owner_name", ""),
                store_data.get("score", 0), store_data.get("status", "discovered"),
            ),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = db.execute("SELECT id FROM stores WHERE place_id = ?", (store_data["place_id"],)).fetchone()
        return row["id"]


def save_reel(store_id: int, garment_id: int, video_path: str, video_url: str, thumbnail_path: str) -> tuple[int, str]:
    import secrets
    watch_token = secrets.token_urlsafe(12)
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO reels (store_id, garment_id, video_path, video_url, thumbnail_path, watch_token)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (store_id, garment_id, video_path, video_url, thumbnail_path, watch_token),
        )
        return cur.lastrowid, watch_token


def record_reel_view(watch_token: str, ip: str, user_agent: str) -> dict | None:
    with get_db() as db:
        reel = db.execute("SELECT id, store_id FROM reels WHERE watch_token = ?", (watch_token,)).fetchone()
        if not reel:
            return None
        db.execute("UPDATE reels SET views = views + 1 WHERE id = ?", (reel["id"],))
        db.execute(
            "INSERT INTO reel_views (reel_id, store_id, ip_address, user_agent) VALUES (?, ?, ?, ?)",
            (reel["id"], reel["store_id"], ip, user_agent),
        )
        return dict(reel)


def get_campaign_stats() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]


def get_stores_for_campaign(campaign_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM stores WHERE campaign_id = ? ORDER BY score DESC",
            (campaign_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_reel_analytics() -> dict:
    with get_db() as db:
        total_views = db.execute("SELECT COALESCE(SUM(views), 0) as total FROM reels").fetchone()["total"]
        total_reels = db.execute("SELECT COUNT(*) as total FROM reels").fetchone()["total"]
        recent_views = db.execute(
            "SELECT COUNT(*) as total FROM reel_views WHERE viewed_at > datetime('now', '-7 days')"
        ).fetchone()["total"]
        return {
            "total_views": total_views,
            "total_reels": total_reels,
            "recent_views_7d": recent_views,
        }
