"""SQLite archive; short independent connections and transactional append-only saves."""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import uuid
from .archive import Evidence


def database_path():
    override=os.environ.get('QUEUEPACT_DB')
    if override:
        path=Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError('QUEUEPACT_DB must be an absolute path')
        return path
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'QueuePact'/'queuepact.sqlite3'


class Repository:
    def __init__(self,path=None):
        self.path=Path(path) if path else database_path()
        if not self.path.is_absolute():
            raise ValueError('Database path must be absolute')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1):
                raise ValueError('Unsupported database schema; keep a backup and use a compatible application')
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, parent_id TEXT REFERENCES records(id), name TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL, students INTEGER NOT NULL, evidence TEXT NOT NULL)')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self,evidence,parent_id=None):
        evidence=Evidence.from_json(evidence.json_text)
        d=evidence.data
        rid=str(uuid.uuid4())
        with self.connection() as db:
            db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)',(rid,parent_id,d['name'],d['kind'],d['created_utc'],d['status'],len(d['runs'][0]['students']),evidence.json_text))
        return rid

    def list(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT id,parent_id,name,kind,created,status,students FROM records ORDER BY created DESC,id LIMIT 500')]

    def get(self,rid):
        with self.connection() as db:
            row=db.execute('SELECT evidence FROM records WHERE id=?',(rid,)).fetchone()
        if row is None:
            raise ValueError('Saved record was not found')
        return Evidence.from_json(row['evidence'],compatible=False)

    def backup(self,path):
        with self.connection() as source, sqlite3.connect(path) as target:
            source.backup(target)
