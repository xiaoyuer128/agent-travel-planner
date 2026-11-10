"""Bounded single-process job runner, SSE replay and atomic final commits."""
import json,time,threading,hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from .runtime import RunContext,running,Cancelled
from .store import Conflict
from .deepseek import ModelUnavailable

POOL=ThreadPoolExecutor(max_workers=4,thread_name_prefix='travel')
JOBS={};LOCK=threading.RLock();MAX_JOBS=64;TTL=900

class Job:
    def __init__(self,owner,sid,revision,fingerprint,key):
        self.id=uuid4().hex;self.owner=owner;self.sid=sid;self.revision=revision
        self.fingerprint=fingerprint;self.key=key;self.created=time.monotonic()
        self.status='queued';self.events=[];self.lock=threading.RLock()
        self.context=RunContext(self.emit);self.result=None
    def emit(self,event,data):
        with self.lock:
            # Coalesce adjacent deltas before allowing an unbounded replay buffer.
            if len(self.events)>=4000:raise Cancelled('输出过长，请缩短问题后重试')
            self.events.append({'id':len(self.events)+1,'event':event,'data':data})

def owned(jid,owner):
    with LOCK:job=JOBS.get(jid)
    if not job or job.owner!=owner:raise HTTPException(404,'任务不存在或已过期')
    return job

def start(owner,sid,turn,db,runner,key=''):
    fingerprint=hashlib.sha256(json.dumps(turn.model_dump(mode='json'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with LOCK:
        for jid,job in list(JOBS.items()):
            if job.status in {'completed','cancelled','failed'} and time.monotonic()-job.created>TTL:del JOBS[jid]
        if key:
            for job in JOBS.values():
                if job.owner==owner and job.key==key:
                    if job.fingerprint!=fingerprint or job.sid!=sid:raise HTTPException(409,'同一请求标识不能用于不同消息')
                    return job
        if any(j.owner==owner and j.sid==sid and j.status in {'queued','running'} for j in JOBS.values()):raise HTTPException(409,'此会话正在生成，请等待或停止当前任务')
        if len(JOBS)>=MAX_JOBS:
            done=[j for j in JOBS.values() if j.status in {'completed','cancelled','failed'}]
            if done:del JOBS[min(done,key=lambda j:j.created).id]
            else:raise HTTPException(429,'生成任务较多，请稍后重试')
        job=Job(owner,sid,turn.revision,fingerprint,key);JOBS[job.id]=job
    def work():
        try:
            with job.lock:job.context.check();job.status='running'
            with running(job.context):
                job.emit('progress',{'stage':'start','label':'已开始处理旅行需求'})
                current=db.get(sid)
                if current['revision']!=turn.revision:raise Conflict('会话已更新，请刷新后重试')
                result=runner(current,turn.message,turn.patch.model_dump(mode='json',exclude_none=True,exclude_unset=True) if turn.patch else {},turn.action,turn.generate)
                # Cancellation and commit are ordered by this lock; no partial state is saved.
                with job.lock:
                    job.context.check();job.result=db.save(result,turn.revision);job.status='completed'
                    job.emit('done',{'session':job.result})
        except Cancelled as exc:
            with job.lock:job.status='cancelled';job.emit('cancelled',{'message':str(exc)})
        except (ModelUnavailable,Conflict) as exc:
            with job.lock:job.status='failed';job.emit('error',{'message':str(exc),'retryable':isinstance(exc,ModelUnavailable)})
        except Exception:
            with job.lock:job.status='failed';job.emit('error',{'message':'任务处理失败，本轮未保存，请稍后重试','retryable':True})
    POOL.submit(work)
    return job

def cancel(job):
    with job.lock:
        if job.status not in {'completed','failed','cancelled'}:job.context.cancel()
        return {'status':job.status,'cancel_requested':job.context.cancelled.is_set()}
