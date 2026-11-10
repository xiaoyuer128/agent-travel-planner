import hashlib,hmac,secrets,time,os,re,json
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field,ConfigDict
from .db import database,init_db

router=APIRouter(prefix='/api/account',tags=['账户'])

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def limit(bucket, count=15, seconds=600):
    init_db()
    now=time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM rate_limits WHERE reset<?',(now,))
        row=db.execute('SELECT * FROM rate_limits WHERE bucket=?',(bucket,)).fetchone()
        if row and row['count']>=count: raise HTTPException(429,'操作频繁，请稍后重试')
        db.execute('INSERT INTO rate_limits VALUES(?,?,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(bucket,1,now+seconds))

def cookie(response,name,value,max_age):
    response.set_cookie(name,value,max_age=max_age,httponly=True,samesite='lax',secure=os.getenv('COOKIE_SECURE','false')=='true',path='/')

def identity(request:Request,response:Response):
    init_db()
    token=request.cookies.get('travel_auth','')
    if token:
        with database() as db:
            user=db.execute('SELECT u.* FROM users u JOIN auth_tokens a ON a.user_id=u.id WHERE a.token=? AND a.expires>?',(digest(token),time.time())).fetchone()
        if user: return {'owner':'u:'+user['id'],'user':dict(user)}
    guest=request.cookies.get('travel_guest','')
    if not re.fullmatch('[a-f0-9]{64}',guest):
        guest=secrets.token_hex(32)
        cookie(response,'travel_guest',guest,60*60*24*30)
    return {'owner':'g:'+digest(guest),'user':None}

def require_user(who=Depends(identity)):
    if not who['user']: raise HTTPException(401,'请先登录后使用此功能')
    return who

def public_user(user):
    if not user:return None
    return {k:user[k] for k in ['id','email','name']} | {'profile':json.loads(user['profile'])}

def admin(who=Depends(require_user)):
    emails={s.strip().lower() for s in os.getenv('ADMIN_EMAILS','').split(',') if s.strip()}
    if who['user']['email'] not in emails: raise HTTPException(403,'仅管理员可操作')
    return who

class Credentials(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=8,max_length=128)
    name:str=Field(default='旅行者',min_length=1,max_length=30)

def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

def authorize(user,response,guest_owner):
    token=secrets.token_urlsafe(32)
    with database() as db:
        db.execute('DELETE FROM auth_tokens WHERE expires<?',(time.time(),))
        db.execute('INSERT INTO auth_tokens VALUES(?,?,?)',(digest(token),user['id'],time.time()+86400*7))
        # Claim only this browser's guest conversations; unowned legacy rows stay private.
        exists=db.execute("SELECT name FROM sqlite_master WHERE name='chat_sessions'").fetchone()
        if exists and 'owner' in [r[1] for r in db.execute('PRAGMA table_info(chat_sessions)')]:
            db.execute('UPDATE chat_sessions SET owner=? WHERE owner=?',('u:'+user['id'],guest_owner))
    cookie(response,'travel_auth',token,86400*7)
    return public_user(user)

@router.get('/me')
def me(who=Depends(identity)):
    emails={s.strip().lower() for s in os.getenv('ADMIN_EMAILS','').split(',')}
    return {'user':public_user(who['user']),'is_admin':bool(who['user'] and who['user']['email'] in emails)}

@router.post('/register',status_code=201)
def register(data:Credentials,request:Request,response:Response,who=Depends(identity)):
    limit('register:'+request.client.host,10,3600)
    email=data.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise HTTPException(422,'邮箱格式不正确')
    user=dict(id=uuid4().hex,email=email,name=data.name.strip() or '旅行者',password=password_hash(data.password),profile='{}',created=time.time())
    import sqlite3
    try:
        with database() as db: db.execute('INSERT INTO users VALUES(:id,:email,:name,:password,:profile,:created)',user)
    except sqlite3.IntegrityError: raise HTTPException(409,'该邮箱已注册')
    return authorize(user,response,who['owner'])

@router.post('/login')
def login(data:Credentials,request:Request,response:Response,who=Depends(identity)):
    limit('login:'+request.client.host,30,600)
    with database() as db: row=db.execute('SELECT * FROM users WHERE email=?',(data.email.strip().lower(),)).fetchone()
    # Always run scrypt, also for unknown accounts.
    stored=row['password'] if row else password_hash('nonexistent-account')
    if not hmac.compare_digest(password_hash(data.password,stored.split(':')[0]),stored) or not row:
        raise HTTPException(401,'邮箱或密码错误')
    return authorize(dict(row),response,who['owner'])

@router.post('/logout')
def logout(request:Request,response:Response):
    init_db()
    with database() as db: db.execute('DELETE FROM auth_tokens WHERE token=?',(digest(request.cookies.get('travel_auth','')),))
    response.delete_cookie('travel_auth',path='/')
    # Rotate guest identity on logout so another user of this device sees no prior guest data.
    cookie(response,'travel_guest',secrets.token_hex(32),86400*30)
    return {'ok':True}

class Profile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=30)
    departure_city:str=Field(default='',max_length=30)
    budget:float|None=Field(default=None,gt=0,le=1000000)
    num_travelers:int=Field(default=2,ge=1,le=10)
    interests:list[str]=Field(default_factory=list,max_length=10)
    pace:str=Field(default='适中',max_length=20)
    transport:str=Field(default='高铁优先',max_length=20)
    walking:str=Field(default='适中',max_length=20)
    needs:str=Field(default='',max_length=300)

@router.put('/profile')
def profile(data:Profile,who=Depends(require_user)):
    payload=data.model_dump(exclude={'name'},exclude_none=True)
    with database() as db: db.execute('UPDATE users SET name=?,profile=? WHERE id=?',(data.name,json.dumps(payload,ensure_ascii=False),who['user']['id']))
    return {**public_user(who['user']),'name':data.name,'profile':payload}
