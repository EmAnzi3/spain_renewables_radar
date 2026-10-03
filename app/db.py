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
  promoter TEXT,
  expediente TEXT,
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
  promoter TEXT,
  expediente TEXT,
  province TEXT,
  ccaa TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(source_code,external_id),
  FOREIGN KEY(project_key) REFERENCES projects(project_key)
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(publication_date);
CREATE INDEX IF NOT EXISTS idx_projects_geo ON projects(ccaa,province);
CREATE INDEX IF NOT EXISTS idx_projects_stage ON projects(commercial_stage,technology);
CREATE INDEX IF NOT EXISTS idx_projects_expediente ON projects(expediente);

CREATE TABLE IF NOT EXISTS project_geo_enrichment (
  project_key TEXT PRIMARY KEY,
  municipalities_json TEXT NOT NULL DEFAULT '[]',
  provinces_json TEXT NOT NULL DEFAULT '[]',
  province TEXT,
  ccaa TEXT,
  status TEXT NOT NULL,
  source_code TEXT NOT NULL,
  source_url TEXT NOT NULL,
  reference_date TEXT,
  enriched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(project_key) REFERENCES projects(project_key)
);
CREATE INDEX IF NOT EXISTS idx_project_geo_status ON project_geo_enrichment(status,province);

CREATE TABLE IF NOT EXISTS ree_node_capacity (
  snapshot_date TEXT NOT NULL,
  node_name TEXT NOT NULL,
  substation_code TEXT,
  ccaa TEXT,
  positions_rdt_existing REAL,
  positions_rdt_planned REAL,
  positions_rdd_existing REAL,
  positions_rdd_planned REAL,
  granted_gen_mw REAL,
  granted_storage_mw REAL,
  pending_gen_mw REAL,
  pending_storage_mw REAL,
  margin_gen_mges_mw REAL,
  margin_gen_mpe_mw REAL,
  margin_storage_mges_mw REAL,
  margin_storage_mpe_mw REAL,
  available_gen_rdt_mges_mw REAL,
  available_gen_rdt_mpe_mw REAL,
  available_gen_rdd_mges_mw REAL,
  available_gen_rdd_mpe_mw REAL,
  available_storage_rdt_mges_mw REAL,
  available_storage_rdt_mpe_mw REAL,
  available_storage_rdd_mges_mw REAL,
  available_storage_rdd_mpe_mw REAL,
  source_url TEXT NOT NULL,
  PRIMARY KEY(snapshot_date,node_name)
);
CREATE INDEX IF NOT EXISTS idx_ree_node_capacity_ccaa ON ree_node_capacity(snapshot_date,ccaa);

CREATE TABLE IF NOT EXISTS miteco_production_registry (
  snapshot_date TEXT NOT NULL,
  autoid TEXT,
  installation_id TEXT,
  regime TEXT,
  installation_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  ccaa TEXT,
  source_url TEXT NOT NULL,
  PRIMARY KEY(snapshot_date,autoid,installation_name)
);
CREATE INDEX IF NOT EXISTS idx_miteco_registry_name ON miteco_production_registry(snapshot_date,normalized_name);
CREATE INDEX IF NOT EXISTS idx_miteco_registry_ccaa ON miteco_production_registry(snapshot_date,ccaa);
"""

def _ensure_column(conn,table,name,definition):
    cols={r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

def connect(db_path:str)->sqlite3.Connection:
    path=Path(db_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path)
    conn.row_factory=sqlite3.Row
    conn.executescript(SCHEMA)
    for table in ("projects","events"):
        _ensure_column(conn,table,"promoter","TEXT")
        _ensure_column(conn,table,"expediente","TEXT")
    conn.commit()
    return conn
