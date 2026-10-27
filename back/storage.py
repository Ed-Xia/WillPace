"""SQLite persistence. Each operation owns its connection, including worker threads."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'posepro.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password TEXT NOT NULL, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS objects (
                    kind TEXT NOT NULL, id TEXT NOT NULL, user_id TEXT NOT NULL,
                    created REAL NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE INDEX IF NOT EXISTS object_owner ON objects(kind,user_id,created);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def password_hash(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()

    def register(self, username, password):
        user_id, salt = secrets.token_hex(16), secrets.token_hex(16)
        profile = {'nickname': username, 'heightCm': 170, 'view': 'auto', 'direction': 'auto', 'calibrationPixels': None}
        with self.connect() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,?)',
                       (user_id, username, salt, self.password_hash(password, salt), json.dumps(profile)))
        return {'id': user_id, 'username': username, 'profile': profile}

    def login(self, username, password):
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        # Equal-cost work for unknown usernames.
        digest = self.password_hash(password, row['salt'] if row else '00' * 16)
        if not row or not secrets.compare_digest(digest, row['password']):
            return None
        return {'id': row['id'], 'username': row['username'], 'profile': json.loads(row['profile'])}

    def session(self, user_id):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + 7 * 86400))
        return token

    def user_for_token(self, token):
        with self.connect() as db:
            row = db.execute('''SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id
                WHERE s.token=? AND s.expires>?''',
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return {'id': row['id'], 'username': row['username'], 'profile': json.loads(row['profile'])} if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))

    def profile(self, user_id, profile):
        with self.connect() as db:
            db.execute('UPDATE users SET profile=? WHERE id=?', (json.dumps(profile, ensure_ascii=False), user_id))

    def put(self, kind, object_id, user_id, data):
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False)
        with self.connect() as db:
            db.execute('''INSERT INTO objects VALUES (?,?,?,?,?) ON CONFLICT(kind,id)
                DO UPDATE SET data=excluded.data''', (kind, object_id, user_id, time.time(), payload))

    def get(self, kind, object_id, user_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND user_id=?',
                             (kind, object_id, user_id)).fetchone()
        return json.loads(row['data']) if row else None

    def list(self, kind, user_id=None):
        with self.connect() as db:
            if user_id is None:
                rows = db.execute('SELECT data FROM objects WHERE kind=? ORDER BY created DESC', (kind,)).fetchall()
            else:
                rows = db.execute('SELECT data FROM objects WHERE kind=? AND user_id=? ORDER BY created DESC',
                                  (kind, user_id)).fetchall()
        return [json.loads(row['data']) for row in rows]

    def delete(self, kind, object_id, user_id):
        with self.connect() as db:
            db.execute('DELETE FROM objects WHERE kind=? AND id=? AND user_id=?', (kind, object_id, user_id))

    def recover_jobs(self):
        for job in self.list('job'):
            if job['status'] in ('queued', 'processing'):
                job.update(status='failed', error='服务中断，点击重试重新分析。')
                self.put('job', job['analysisId'], job['userId'], job)
