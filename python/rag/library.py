"""Persistent, editable RAG library using Chinese n-gram FTS5/BM25 retrieval."""
import re,time,json,hashlib
from uuid import uuid4
from community.db import database,init_db
from domestic import GUIDES

def tokens(text):
    words=re.findall(r'[a-zA-Z0-9]+',text.lower())
    for run in re.findall(r'[\u4e00-\u9fff]+',text):
        words.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run)==1:words.append(run)
    return list(dict.fromkeys(words))

def initialize():
    init_db()
    with database() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS knowledge_docs(id TEXT PRIMARY KEY,title TEXT NOT NULL,city TEXT NOT NULL,source TEXT NOT NULL,url TEXT NOT NULL,body TEXT NOT NULL,version TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS knowledge_chunks(id TEXT PRIMARY KEY,doc_id TEXT NOT NULL REFERENCES knowledge_docs(id) ON DELETE CASCADE,text TEXT NOT NULL,position INTEGER NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(chunk_id UNINDEXED, terms, tokenize='unicode61');
        CREATE TABLE IF NOT EXISTS knowledge_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
        if not db.execute("SELECT 1 FROM knowledge_meta WHERE key='seed-v1'").fetchone():
            for guide in GUIDES:
                _insert(db,guide['id'],guide['title'],guide['city'],'内置编辑参考资料','',guide['text'],'1')
            _insert(db,'travel-basics','国内旅行准备与信息核实','','平台编辑参考资料','',
                '国内旅行建议提前核实景区开放、预约、交通与住宿信息。历史照片不能反映当天景色。带老人或儿童出行应减少连续步行、预留休息。雨天可以选择博物馆等室内活动，具体开放以场馆公告为准。','1')
            db.execute("INSERT INTO knowledge_meta VALUES('seed-v1','1')")

def _insert(db,did,title,city,source,url,body,version):
    db.execute('INSERT INTO knowledge_docs VALUES(?,?,?,?,?,?,?,?)',(did,title,city,source,url,body,version,time.time()))
    # Overlapping chunks keep adjacent sentences available without an unbounded prompt.
    for i,start in enumerate(range(0,len(body),500)):
        text=body[start:start+650];cid=did+':'+str(i)
        db.execute('INSERT INTO knowledge_chunks VALUES(?,?,?,?)',(cid,did,text,i))
        db.execute('INSERT INTO knowledge_fts VALUES(?,?)',(cid,' '.join(tokens(title+' '+city+' '+text))))

def ingest(title,city,source,url,body):
    initialize();did=uuid4().hex
    with database() as db:_insert(db,did,title,city,source,url,body,'1')
    return did

def remove(did):
    initialize()
    with database() as db:
        db.execute('DELETE FROM knowledge_fts WHERE chunk_id IN(SELECT id FROM knowledge_chunks WHERE doc_id=?)',(did,))
        db.execute('DELETE FROM knowledge_docs WHERE id=?',(did,))

def search(query,city='',limit=4):
    initialize()
    terms=tokens(query)[:70]
    if not terms:return []
    match=' OR '.join('"'+t.replace('"','')+'"' for t in terms)
    with database() as db:
        sql='''SELECT c.id,c.text,d.title,d.city,d.source,d.url,d.version,bm25(knowledge_fts) AS rank
            FROM knowledge_fts JOIN knowledge_chunks c ON c.id=knowledge_fts.chunk_id JOIN knowledge_docs d ON d.id=c.doc_id
            WHERE knowledge_fts MATCH ?'''
        args=[match]
        if city:sql+=' AND (d.city=? OR d.city=\'\')';args.append(city)
        sql+=' ORDER BY rank LIMIT ?';args.append(max(1,min(limit,8)))
        rows=db.execute(sql,args).fetchall()
    return [{'id':r['id'],'text':r['text'],'title':r['title'],'city':r['city'],'source':r['source'],
             'uri':r['url'] or 'knowledge://'+r['id'],'version':r['version'],'score':round(-r['rank'],6)} for r in rows]
