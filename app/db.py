from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA="""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS projects (
  project_key TEXT PRIMARY KEY,
  project_name TEXT,
  technology TEXT,
  power_mw REAL,
  province TEXT,
  ccaa TEXT,
  commercial_stage TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  latest_event_type TEXT NOT NULL,
  latest_source_code TEXT,
  latest_source_url TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_code TEXT NOT NULL,
  external_id TEXT NOT NULL,
  publication_date TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  raw_text TEXT,
  project_key TEXT NOT NULL,
  event_type TEXT NOT NULL,
  commercial_stage TEXT NOT NULL,
  technology TEXT,
  power_mw REAL,
  province TEXT,
  ccaa TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(source_code,external_id),
  FOREIGN KEY(project_key) REFERENCES projects(project_key)
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(publication_date);
CREATE INDEX IF NOT EXISTS idx_projects_geo ON projects(ccaa,province);
CREATE INDEX IF NOT EXISTS idx_projects_stage ON projects(commercial_stage,technology);
"""

def connect(db_path:str)->sqlite3.Connection:
    path=Path(db_path);path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row;conn.executescript(SCHEMA)
    return conn
