import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

def data_dir():
    return Path(os.getenv('CHAT_DB_PATH',str(Path(__file__).resolve().parents[1]/'data/chat.sqlite3'))).parent

@contextmanager
def database():
    path=Path(os.getenv('CHAT_DB_PATH',str(data_dir()/'chat.sqlite3')))
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=15)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn: yield conn
    finally: conn.close()

def init_db():
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,profile TEXT NOT NULL DEFAULT '{}',created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_tokens(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS folders(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,UNIQUE(owner,name));
        CREATE TABLE IF NOT EXISTS favorites(id TEXT PRIMARY KEY,owner TEXT NOT NULL,folder_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,kind TEXT NOT NULL,city TEXT NOT NULL,name TEXT NOT NULL,target TEXT NOT NULL,image TEXT,created REAL NOT NULL,UNIQUE(owner,kind,target));
        CREATE TABLE IF NOT EXISTS feedback(owner TEXT NOT NULL,target TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(owner,target));
        CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,owner TEXT NOT NULL,filename TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY,owner TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,city TEXT NOT NULL,travel_date TEXT,visibility TEXT NOT NULL,status TEXT NOT NULL,images TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,owner TEXT NOT NULL,post_id TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS moderation_log(id TEXT PRIMARY KEY,actor TEXT NOT NULL,post_id TEXT NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS shares(token TEXT PRIMARY KEY,owner TEXT NOT NULL,session_id TEXT NOT NULL,snapshot TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS checklists(session_id TEXT NOT NULL,owner TEXT NOT NULL,items TEXT NOT NULL,PRIMARY KEY(session_id,owner));
        CREATE TABLE IF NOT EXISTS rate_limits(bucket TEXT PRIMARY KEY,count INTEGER NOT NULL,reset REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS posts_feed ON posts(visibility,status,created);
        CREATE INDEX IF NOT EXISTS favorites_owner ON favorites(owner,created);
        ''')
