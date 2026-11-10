from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from community.auth import admin,identity,limit
from community.db import database
from rag.library import initialize,ingest,remove,search
import json,time
from uuid import uuid4
from rag.evaluation import evaluate

router=APIRouter(prefix='/api/knowledge',tags=['RAG 知识库'])

class Document(BaseModel):
    title:str=Field(min_length=1,max_length=120)
    city:str=Field(default='',max_length=30)
    source:str=Field(min_length=1,max_length=120)
    url:str=Field(default='',max_length=1000)
    body:str=Field(min_length=20,max_length=100000)

@router.get('/search')
def retrieve(q:str=Query(min_length=1,max_length=500),city:str='',who=Depends(identity)):
    limit('knowledge:'+who['owner'],120,3600)
    return {'sources':search(q,city),'retriever':'中文查询扩展 + BM25 / 字符TF-IDF + RRF + 重排'}

@router.get('/documents')
def documents(who=Depends(admin)):
    initialize()
    with database() as db:return [dict(r) for r in db.execute('SELECT id,title,city,source,url,version,length(body) AS characters FROM knowledge_docs ORDER BY created DESC')]

@router.post('/documents',status_code=201)
def create(data:Document,who=Depends(admin)):
    if data.url and not data.url.startswith(('https://','http://')):raise HTTPException(422,'来源链接仅支持 http/https')
    return {'id':ingest(data.title,data.city,data.source,data.url,data.body),'indexed':True}

@router.delete('/documents/{did}')
def delete(did:str,who=Depends(admin)):
    remove(did);return {'ok':True}

def evaluations_table():
    initialize()
    with database() as db:db.execute('CREATE TABLE IF NOT EXISTS rag_evaluations(id TEXT PRIMARY KEY,created REAL NOT NULL,report TEXT NOT NULL)')

@router.post('/evaluations',status_code=201)
def run_evaluation(who=Depends(admin)):
    limit('rag-eval:'+who['owner'],6,3600)
    report=evaluate();eid=uuid4().hex;evaluations_table()
    with database() as db:db.execute('INSERT INTO rag_evaluations VALUES(?,?,?)',(eid,time.time(),json.dumps(report,ensure_ascii=False)))
    return {'id':eid,'report':report}

@router.get('/evaluations')
def list_evaluations(who=Depends(admin)):
    evaluations_table()
    with database() as db:return [{'id':r['id'],'created':r['created'],'report':json.loads(r['report'])} for r in db.execute('SELECT * FROM rag_evaluations ORDER BY created DESC LIMIT 10')]

@router.get('/evaluations/{eid}')
def get_evaluation(eid:str,who=Depends(admin)):
    evaluations_table()
    with database() as db:row=db.execute('SELECT report FROM rag_evaluations WHERE id=?',(eid,)).fetchone()
    if not row:raise HTTPException(404,'评测记录不存在')
    return json.loads(row['report'])
