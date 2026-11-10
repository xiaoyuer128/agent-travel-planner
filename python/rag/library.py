"""Persistent, editable RAG library using Chinese n-gram FTS5/BM25 retrieval."""
import re,time,json,hashlib,math
from collections import Counter
from uuid import uuid4
from community.db import database,init_db
from domestic import GUIDES

def tokens(text):
    words=re.findall(r'[a-zA-Z0-9]+',text.lower())
    for run in re.findall(r'[\u4e00-\u9fff]+',text):
        words.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run)==1:words.append(run)
    return list(dict.fromkeys(words))

def initialize(db_path=None):
    init_db(db_path)
    with database(db_path) as db:
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

def ingest(title,city,source,url,body,db_path=None):
    initialize(db_path);did=uuid4().hex
    with database(db_path) as db:_insert(db,did,title,city,source,url,body,'1')
    return did

def remove(did):
    initialize()
    with database() as db:
        db.execute('DELETE FROM knowledge_fts WHERE chunk_id IN(SELECT id FROM knowledge_chunks WHERE doc_id=?)',(did,))
        db.execute('DELETE FROM knowledge_docs WHERE id=?',(did,))

def bm25_search(query,city='',limit=4,db_path=None):
    initialize(db_path)
    terms=tokens(query)[:70]
    if not terms:return []
    match=' OR '.join('"'+t.replace('"','')+'"' for t in terms)
    with database(db_path) as db:
        sql='''SELECT c.id,c.text,d.title,d.city,d.source,d.url,d.version,bm25(knowledge_fts) AS rank
            FROM knowledge_fts JOIN knowledge_chunks c ON c.id=knowledge_fts.chunk_id JOIN knowledge_docs d ON d.id=c.doc_id
            WHERE knowledge_fts MATCH ?'''
        args=[match]
        if city:sql+=' AND (d.city=? OR d.city=\'\')';args.append(city)
        sql+=' ORDER BY rank LIMIT ?';args.append(max(1,min(limit,30)))
        rows=db.execute(sql,args).fetchall()
    return [{'id':r['id'],'text':r['text'],'title':r['title'],'city':r['city'],'source':r['source'],
             'uri':r['url'] or 'knowledge://'+r['id'],'version':r['version'],'score':round(-r['rank'],6)} for r in rows]


# Domain query expansion is an explicit rule set, not a claimed semantic model.
ALIASES={
 '不费腿':'少走路 平缓 步行 休息', '少走路':'步行 休息 轻松', '带老人':'步行 休息 轻松',
 '遛娃':'亲子 儿童 公园', '下雨':'雨天 室内 博物馆', '雨天':'室内 博物馆',
 '湖边':'湖畔 湖泊', '海边':'海滨 滨海', '逛吃':'美食 街区', '老建筑':'历史 文化',
 '看海':'海滨 滨海 海岛', '古建筑':'文化 历史 古城', '夜景':'夜晚 城市',
}

def expand(query):return query+' '+' '.join(value for key,value in ALIASES.items() if key in query)

def features(text):
    # Sparse character/word vectors retain lexical overlap when bigram segmentation differs.
    chars=Counter(c for c in text if '\u4e00'<=c<='\u9fff')
    chars.update(tokens(text))
    return chars

def search(query,city='',limit=4,strategy='hybrid',db_path=None):
    if strategy=='bm25':return bm25_search(query,city,limit,db_path)
    initialize(db_path)
    expanded=expand(query);lexical=bm25_search(expanded,city,24,db_path)
    with database(db_path) as db:
        sql='SELECT c.id,c.text,d.title,d.city,d.source,d.url,d.version FROM knowledge_chunks c JOIN knowledge_docs d ON d.id=c.doc_id'
        args=[]
        if city:sql+=" WHERE d.city=? OR d.city=''";args.append(city)
        sql+=' ORDER BY d.created DESC,c.position LIMIT 5000'
        rows=[dict(r) for r in db.execute(sql,args)]
    if not rows:return []
    docs=[features(r['title']+' '+r['city']+' '+r['text']) for r in rows]
    df=Counter(term for doc in docs for term in doc)
    idf={term:math.log((len(docs)+1)/(n+1))+1 for term,n in df.items()}
    q={term:count*idf.get(term,1) for term,count in features(expanded).items()}
    qnorm=math.sqrt(sum(v*v for v in q.values())) or 1
    vectors=[]
    for row,doc in zip(rows,docs):
        # Do not let a single shared character turn an unrelated query into a citation.
        if not set(tokens(expanded)) & set(tokens(row['title']+' '+row['city']+' '+row['text'])):continue
        vec={term:(1+math.log(count))*idf[term] for term,count in doc.items()}
        norm=math.sqrt(sum(v*v for v in vec.values())) or 1
        score=sum(q.get(t,0)*v for t,v in vec.items())/(qnorm*norm)
        if score>=.08:vectors.append((score,row))
    vectors.sort(key=lambda x:-x[0]);vectors=vectors[:24]
    ranks={};items={};vector_scores={}
    for rank,item in enumerate(lexical,1):ranks[item['id']]=ranks.get(item['id'],0)+1/(60+rank);items[item['id']]=item
    for rank,(score,row) in enumerate(vectors,1):
        cid=row['id'];vector_scores[cid]=score;ranks[cid]=ranks.get(cid,0)+1/(60+rank)
        items.setdefault(cid,{'id':cid,'text':row['text'],'title':row['title'],'city':row['city'],'source':row['source'],'uri':row['url'] or 'knowledge://'+cid,'version':row['version'],'score':score})
    query_terms=set(tokens(query));out=[];seen=set()
    def rerank(cid):
        title=set(tokens(items[cid]['title']));coverage=len(title&query_terms)/max(1,len(query_terms))
        return ranks[cid]+.018*coverage+(.006 if city and items[cid]['city']==city else 0)
    for cid in sorted(ranks,key=rerank,reverse=True):
        doc=cid.rsplit(':',1)[0]
        if doc in seen:continue
        seen.add(doc)
        out.append({**items[cid],'score':round(rerank(cid),6),'retriever':'hybrid-bm25-tfidf-rrf','lexical_similarity':round(vector_scores.get(cid,0),4)})
        if len(out)>=max(1,min(limit,8)):break
    return out
