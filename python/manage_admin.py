"""本地管理员配置工具：python manage_admin.py 已注册的邮箱。"""
from pathlib import Path
import sys,re
from dotenv import load_dotenv
from community.db import init_db,database

if __name__=='__main__':
    load_dotenv(Path(__file__).parent/'.env')
    if len(sys.argv)!=2:raise SystemExit('用法：python manage_admin.py 已注册的邮箱')
    email=sys.argv[1].strip().lower()
    init_db()
    with database() as db:
        if not db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone():raise SystemExit('该邮箱尚未注册，请先在网站注册')
    path=Path(__file__).parent/'.env';text=path.read_text(encoding='utf-8') if path.exists() else ''
    match=re.search(r'^ADMIN_EMAILS=(.*)$',text,re.M)
    emails={x.strip() for x in match[1].split(',')} if match else set()
    emails.add(email);text=re.sub(r'^ADMIN_EMAILS=.*\n?','',text,flags=re.M)
    path.write_text(text.rstrip()+'\nADMIN_EMAILS='+','.join(sorted(emails))+'\n',encoding='utf-8')
    print('管理员邮箱已配置，重启后端后重新登录即可进入内容管理。')
