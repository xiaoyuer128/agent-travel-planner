"""Portable, offline tests: never use real credentials or the application database."""
import os
import sys
from pathlib import Path
import pytest

os.environ['LLM_PROVIDER']='mock'
os.environ['RAG_EMBEDDING']='mock'
os.environ['RAG_STORE']='memory'
os.environ['LANGSMITH_TRACING']='false'
os.environ['AMAP_API_KEY']=''
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

@pytest.fixture(autouse=True)
def isolated_database(tmp_path,monkeypatch):
    monkeypatch.setenv('CHAT_DB_PATH',str(tmp_path/'chat.sqlite3'))
