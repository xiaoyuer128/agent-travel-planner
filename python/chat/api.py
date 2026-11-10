import os
from copy import deepcopy
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from .models import Turn
from .store import SessionStore, Conflict
from .graph import run_turn
from .deepseek import ModelUnavailable
from config.settings import settings
from community.auth import identity, limit
import json

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.get('/config')
def config():
    return {'provider': settings.LLM_PROVIDER, 'model': settings.LLM_MODEL if settings.LLM_PROVIDER != 'mock' else None}


def store(who=None):
    return SessionStore(os.getenv("CHAT_DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "chat.sqlite3")), (who or {}).get('owner','legacy'))


@router.get("/sessions")
def sessions(who=Depends(identity)):
    return store(who).list()


@router.post("/sessions", status_code=201)
def create_session(who=Depends(identity)):
    db=store(who)
    s=db.create()
    if who['user']:
        profile=json.loads(who['user']['profile'])
        s['preferences']={k:v for k,v in profile.items() if v not in ('',None,[]) and k in ['departure_city','budget','num_travelers','interests','pace','transport','walking','needs']}
        if s['preferences']:s=db.save(s,0)
    return s


@router.get("/sessions/{session_id}")
def get_session(session_id: str,who=Depends(identity)):
    try:
        return store(who).get(session_id)
    except KeyError:
        raise HTTPException(404, "会话不存在")


@router.post("/sessions/{session_id}/messages")
def message(session_id: str, turn: Turn,who=Depends(identity)):
    current = get_session(session_id,who)
    if current["revision"] != turn.revision:
        raise HTTPException(409, "会话已更新，请刷新后重试")
    if not turn.message.strip():
        raise HTTPException(422, "消息不能为空")
    if len(current["messages"]) >= 200:
        raise HTTPException(422, "本会话已达100轮，请新建会话")
    limit('model:'+who['owner'],30,3600)
    try:
        updated = run_turn(current, turn.message, turn.patch.model_dump(mode="json", exclude_unset=True, exclude_none=True) if turn.patch else {}, turn.action,turn.generate)
    except ModelUnavailable as exc:
        raise HTTPException(502, str(exc))
    try:
        return store(who).save(updated, turn.revision)
    except Conflict as exc:
        raise HTTPException(409, str(exc))


@router.post("/sessions/{session_id}/restore/{version}")
def restore(session_id: str, version: int, turn: Turn,who=Depends(identity)):
    current = get_session(session_id,who)
    if not 1 <= version <= len(current["versions"]):
        raise HTTPException(404, "方案版本不存在")
    if len(current["versions"]) >= 100:
        raise HTTPException(422, "版本过多，请新建会话")
    plan = deepcopy(current["versions"][version-1])
    plan["version"] = len(current["versions"]) + 1
    plan["changed_sections"] = ["restore"]
    current["plan"] = plan
    current["preferences"] = deepcopy(plan["preferences"])
    current["versions"].append(deepcopy(plan))
    current["title"] = f"{plan['preferences']['destination']} · {plan['preferences']['days']}天"
    current["messages"].append({"role": "assistant", "content": f"已从v{version}恢复，保存为v{plan['version']}。"})
    try:
        return store(who).save(current, turn.revision)
    except Conflict as exc:
        raise HTTPException(409, str(exc))
