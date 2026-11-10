from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from community.auth import admin,identity,limit
from community.db import database
from rag.library import initialize,ingest,remove,search

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
    return {'sources':search(q,city),'retriever':'SQLite FTS5 / BM25 + 中文双字切分'}

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
