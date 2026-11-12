"""Shared tap total. No identities, IP addresses or credentials are stored."""
import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path
from uuid import UUID
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

class HeartTaps(BaseModel):
    tap_ids: list[UUID] = Field(min_length=1, max_length=100)

class HeartStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('HEARTS_DB_PATH') or Path(tempfile.gettempdir()) / 'gnani-hearts.sqlite3')

    def update(self, tap_ids=()):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('CREATE TABLE IF NOT EXISTS heart_total (id INTEGER PRIMARY KEY CHECK(id=1), count INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS heart_taps (id TEXT PRIMARY KEY, created INTEGER NOT NULL DEFAULT (unixepoch()))')
            db.execute('INSERT OR IGNORE INTO heart_total VALUES (1,0)')
            added = 0
            for tap_id in tap_ids:
                added += db.execute('INSERT OR IGNORE INTO heart_taps(id) VALUES (?)', (str(tap_id),)).rowcount
            if added:
                db.execute('UPDATE heart_total SET count=count+? WHERE id=1', (added,))
                db.execute('DELETE FROM heart_taps WHERE created < unixepoch()-86400')
            count = db.execute('SELECT count FROM heart_total WHERE id=1').fetchone()[0]
            return {'count': count}

def install(app, path=None):
    store = HeartStore(path)
    async def call(ids=()):
        try:
            value = await asyncio.to_thread(store.update, ids)
            return JSONResponse(value, headers={'Cache-Control':'no-store'})
        except (sqlite3.Error, OSError):
            raise HTTPException(503, 'The shared heart counter is unavailable. Please try again.')

    @app.get('/api/hearts')
    async def get_hearts():
        return await call()

    @app.post('/api/hearts')
    async def add_hearts(body: HeartTaps):
        return await call(body.tap_ids)
