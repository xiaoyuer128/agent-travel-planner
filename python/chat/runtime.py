"""Per-run progress and cooperative cancellation, isolated across worker threads."""
from contextvars import ContextVar
from contextlib import contextmanager
from threading import Event,RLock
import time,json,re

CURRENT=ContextVar('travel_run',default=None)
OUTPUT=ContextVar('travel_output',default='')

class Cancelled(Exception):pass

class RunContext:
    def __init__(self,emit=None,timeout=180):
        self.emit=emit or (lambda event,data:None)
        self.cancelled=Event();self.deadline=time.monotonic()+timeout
        self.closers=[];self.lock=RLock()
    def check(self):
        if self.cancelled.is_set():raise Cancelled('已停止生成，未保存本轮草稿')
        if time.monotonic()>self.deadline:raise Cancelled('任务超时，未保存本轮草稿')
    def cancel(self):
        self.cancelled.set()
        with self.lock:
            for close in list(self.closers):
                try:close()
                except Exception:pass
    @contextmanager
    def closing(self,close):
        with self.lock:self.closers.append(close)
        try:self.check();yield
        finally:
            with self.lock:
                if close in self.closers:self.closers.remove(close)

@contextmanager
def running(context):
    token=CURRENT.set(context)
    try:context.check();yield
    finally:CURRENT.reset(token)

@contextmanager
def output_field(name):
    token=OUTPUT.set(name)
    try:yield
    finally:OUTPUT.reset(token)

def check():
    context=CURRENT.get()
    if context:context.check()

def progress(stage,label,**data):
    check();context=CURRENT.get()
    if context:context.emit('progress',{'stage':stage,'label':label,**data})

def partial_json_string(text,field='reply'):
    """Decode only complete JSON string characters; never render the raw JSON envelope."""
    match=re.search(r'"'+re.escape(field)+r'"\s*:\s*"',text)
    if not match:return ''
    raw=text[match.end():];escaped=False;end=len(raw)
    for i,char in enumerate(raw):
        if not escaped and char=='"':end=i;break
        if not escaped and char=='\\':escaped=True
        else:escaped=False
    raw=raw[:end]
    for trim in range(min(8,len(raw))+1):
        candidate=raw if trim==0 else raw[:-trim]
        try:return json.loads('"'+candidate+'"').encode('utf-8','ignore').decode('utf-8')
        except json.JSONDecodeError:continue
    return ''
