import io,json,time,secrets,warnings,os
from uuid import uuid4
from datetime import date
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import Response,FileResponse
from pydantic import BaseModel,Field,ConfigDict
from PIL import Image,ImageOps,UnidentifiedImageError
from .db import database,data_dir
from .auth import require_user,identity,admin,limit
from domestic import PLACES

router=APIRouter(prefix='/api',tags=['收藏与社区'])

class Folder(BaseModel):name:str=Field(min_length=1,max_length=30)

@router.get('/folders')
def folders(who=Depends(require_user)):
    with database() as db:return [dict(r) for r in db.execute('SELECT * FROM folders WHERE owner=? ORDER BY name',(who['owner'],))]

@router.post('/folders',status_code=201)
def create_folder(data:Folder,who=Depends(require_user)):
    import sqlite3
    fid=uuid4().hex
    try:
        with database() as db:db.execute('INSERT INTO folders VALUES(?,?,?)',(fid,who['owner'],data.name.strip()))
    except sqlite3.IntegrityError: raise HTTPException(409,'收藏夹已存在')
    return {'id':fid,'name':data.name.strip()}

@router.delete('/folders/{fid}')
def delete_folder(fid:str,who=Depends(require_user)):
    with database() as db:db.execute('DELETE FROM folders WHERE id=? AND owner=?',(fid,who['owner']))
    return {'ok':True}

class Favorite(BaseModel):
    folder_id:str
    kind:str=Field(pattern='^(spot|city|post|route)$')
    city:str=Field(max_length=30)
    name:str=Field(min_length=1,max_length=100)
    target:str=Field(min_length=1,max_length=200)
    image:str|None=Field(default=None,max_length=1000)

@router.get('/favorites')
def favorites(who=Depends(require_user)):
    with database() as db:return [dict(r) for r in db.execute('SELECT * FROM favorites WHERE owner=? ORDER BY created DESC',(who['owner'],))]

@router.post('/favorites')
def favorite(data:Favorite,who=Depends(require_user)):
    with database() as db:
        if not db.execute('SELECT id FROM folders WHERE id=? AND owner=?',(data.folder_id,who['owner'])).fetchone():raise HTTPException(404,'收藏夹不存在')
        image=data.image if data.image and data.image.startswith(('https://','/api/media/')) else None
        fid=uuid4().hex
        db.execute('INSERT INTO favorites VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(owner,kind,target) DO UPDATE SET folder_id=excluded.folder_id',
            (fid,who['owner'],data.folder_id,data.kind,data.city,data.name,data.target,image,time.time()))
    return {'ok':True}

@router.delete('/favorites/{fid}')
def unfavorite(fid:str,who=Depends(require_user)):
    with database() as db:db.execute('DELETE FROM favorites WHERE id=? AND owner=?',(fid,who['owner']))
    return {'ok':True}

class Feedback(BaseModel):
    target:str=Field(min_length=1,max_length=100)
    value:str=Field(pattern='^(want|visited|hide)$')

@router.get('/feedback')
def feedback_list(who=Depends(require_user)):
    with database() as db:return {r['target']:r['value'] for r in db.execute('SELECT * FROM feedback WHERE owner=?',(who['owner'],))}

@router.post('/feedback')
def feedback(data:Feedback,who=Depends(require_user)):
    with database() as db:db.execute('INSERT INTO feedback VALUES(?,?,?) ON CONFLICT(owner,target) DO UPDATE SET value=excluded.value',(who['owner'],data.target,data.value))
    return {'ok':True}

@router.delete('/feedback/{target}')
def feedback_delete(target:str,who=Depends(require_user)):
    with database() as db:db.execute('DELETE FROM feedback WHERE owner=? AND target=?',(who['owner'],target))
    return {'ok':True}

@router.post('/uploads',status_code=201)
async def upload(request:Request,who=Depends(require_user)):
    limit('upload:'+who['owner'],30,3600)
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>8*1024*1024:raise HTTPException(413,'图片不能超过 8 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in {'JPEG','PNG','WEBP'}:raise ValueError('unsupported')
                if original.width*original.height>25_000_000:raise ValueError('too large')
                original.load()
                image=ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1920,1920))
                # Fresh pixels strip EXIF, GPS and other source metadata.
                clean=Image.new('RGB',image.size);clean.paste(image)
                folder=data_dir()/'uploads';folder.mkdir(parents=True,exist_ok=True)
                uid=uuid4().hex
                clean.save(folder/(uid+'.jpg'),'JPEG',quality=85)
                clean.thumbnail((480,480));clean.save(folder/(uid+'.thumb.jpg'),'JPEG',quality=80)
                width,height=image.size
    except (UnidentifiedImageError,ValueError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'仅支持有效 JPEG、PNG、WebP 图片，像素不得超过 2500 万') from None
    with database() as db:db.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?)',(uid,who['owner'],uid+'.jpg',width,height,time.time()))
    return {'id':uid,'url':'/api/media/'+uid,'thumbnail':'/api/media/'+uid+'?thumb=true','width':width,'height':height}

@router.get('/media/{uid}')
def media(uid:str,thumb:bool=False,who=Depends(identity)):
    with database() as db:
        row=db.execute('SELECT * FROM uploads WHERE id=?',(uid,)).fetchone()
        if not row:raise HTTPException(404,'图片不存在')
        is_admin=bool(who['user'] and who['user']['email'] in {s.strip().lower() for s in os.getenv('ADMIN_EMAILS','').split(',') if s.strip()})
        if row['owner']!=who['owner'] and not is_admin:
            public=db.execute("SELECT images FROM posts WHERE visibility='public' AND status='approved'").fetchall()
            if not any(uid in json.loads(r['images']) for r in public):raise HTTPException(404,'图片不存在')
    file=data_dir()/'uploads'/(uid+('.thumb.jpg' if thumb else '.jpg'))
    if not file.exists():raise HTTPException(404,'图片不存在')
    return FileResponse(file,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=0, must-revalidate','X-Content-Type-Options':'nosniff'})

class Post(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=80)
    body:str=Field(min_length=1,max_length=5000)
    city:str=Field(min_length=1,max_length=30)
    travel_date:date|None=None
    visibility:str=Field(default='private',pattern='^(private|public)$')
    submit:bool=False
    images:list[str]=Field(default_factory=list,max_length=9)

def post_view(row):
    item=dict(row);item['images']=json.loads(item['images'])
    item.pop('owner',None)
    return item

@router.get('/posts')
def posts(mine:bool=False,city:str='',who=Depends(identity)):
    if mine and not who['user']:raise HTTPException(401,'请先登录')
    with database() as db:
        where,args=('p.owner=?',[who['owner']]) if mine else ("p.visibility='public' AND p.status='approved'",[])
        if city:where+=' AND p.city=?';args.append(city)
        rows=db.execute(f'SELECT p.*,u.name AS author FROM posts p JOIN users u ON p.owner=\'u:\'||u.id WHERE {where} ORDER BY p.created DESC LIMIT 100',args).fetchall()
    return [post_view(r) for r in rows]

@router.get('/posts/{pid}')
def post_detail(pid:str,who=Depends(identity)):
    with database() as db:row=db.execute('SELECT p.*,u.name AS author FROM posts p JOIN users u ON p.owner=\'u:\'||u.id WHERE p.id=?',(pid,)).fetchone()
    if not row or (row['owner']!=who['owner'] and (row['visibility']!='public' or row['status']!='approved')):raise HTTPException(404,'游记不存在')
    return post_view(row)

def save_post(data,who,pid=None):
    if data.travel_date and data.travel_date>date.today():raise HTTPException(422,'拍摄日期不能晚于今天')
    status='pending' if data.visibility=='public' and data.submit else 'draft'
    with database() as db:
        if pid and not db.execute('SELECT id FROM posts WHERE id=? AND owner=?',(pid,who['owner'])).fetchone():raise HTTPException(404,'游记不存在')
        for uid in data.images:
            if not db.execute('SELECT id FROM uploads WHERE id=? AND owner=?',(uid,who['owner'])).fetchone():raise HTTPException(422,'图片不存在或不属于你')
        now=time.time()
        if pid:
            db.execute('UPDATE posts SET title=?,body=?,city=?,travel_date=?,visibility=?,status=?,images=?,updated=? WHERE id=?',
                (data.title,data.body,data.city,str(data.travel_date) if data.travel_date else None,data.visibility,status,json.dumps(data.images),now,pid))
        else:
            pid=uuid4().hex
            db.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (pid,who['owner'],data.title,data.body,data.city,str(data.travel_date) if data.travel_date else None,data.visibility,status,json.dumps(data.images),now,now))
    return {'id':pid,'status':status}

@router.post('/posts',status_code=201)
def create_post(data:Post,who=Depends(require_user)):
    limit('post:'+who['owner'],20,3600)
    return save_post(data,who)

@router.put('/posts/{pid}')
def edit_post(pid:str,data:Post,who=Depends(require_user)):return save_post(data,who,pid)

@router.delete('/posts/{pid}')
def delete_post(pid:str,who=Depends(require_user)):
    with database() as db:
        db.execute('DELETE FROM reports WHERE post_id=? AND EXISTS(SELECT 1 FROM posts WHERE id=? AND owner=?)',(pid,pid,who['owner']))
        db.execute('DELETE FROM posts WHERE id=? AND owner=?',(pid,who['owner']))
    return {'ok':True}

class Report(BaseModel):reason:str=Field(min_length=2,max_length=300)
@router.post('/posts/{pid}/report')
def report(pid:str,data:Report,who=Depends(require_user)):
    post_detail(pid,who)
    limit('report:'+who['owner'],20,3600)
    with database() as db:db.execute('INSERT INTO reports VALUES(?,?,?,?,?,?)',(uuid4().hex,who['owner'],pid,data.reason,'open',time.time()))
    return {'ok':True}

@router.get('/admin/queue')
def queue(who=Depends(admin)):
    with database() as db:
        pending=[post_view(r) for r in db.execute("SELECT * FROM posts WHERE status='pending' ORDER BY updated")]
        reports=[dict(r) for r in db.execute("SELECT r.*,p.title FROM reports r LEFT JOIN posts p ON r.post_id=p.id WHERE r.status='open'")]
    return {'posts':pending,'reports':reports}

class Review(BaseModel):
    decision:str=Field(pattern='^(approved|rejected|hidden)$')
    note:str=Field(default='',max_length=300)

@router.post('/admin/posts/{pid}/review')
def review(pid:str,data:Review,who=Depends(admin)):
    with database() as db:
        if not db.execute('SELECT id FROM posts WHERE id=?',(pid,)).fetchone():raise HTTPException(404,'游记不存在')
        db.execute('UPDATE posts SET status=?,updated=? WHERE id=?',(data.decision,time.time(),pid))
        db.execute('UPDATE reports SET status=? WHERE post_id=?',('resolved',pid))
        db.execute('INSERT INTO moderation_log VALUES(?,?,?,?,?,?)',(uuid4().hex,who['owner'],pid,data.decision,data.note,time.time()))
    return {'ok':True}
