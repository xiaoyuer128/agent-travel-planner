from fastapi.testclient import TestClient
from api.app import app
from api import discover
from domestic import PLACES

def test_domestic_live_photos_and_city_filter(monkeypatch):
    discover._cache.clear()
    monkeypatch.setenv('AMAP_API_KEY', 'test-only')
    calls = []
    async def query(city, name, key):
        calls.append((city,name))
        return {'id': 'poi', 'name': name, 'address': '景点地址',
                'photos': [{'url':'https://example.com/photo.jpg'}]}, None
    monkeypatch.setattr(discover, 'query_amap', query)
    with TestClient(app) as c:
        r = c.get('/api/discover/spots', params={'city':'杭州'}).json()
        assert r['mode'] == 'live'
        assert all(s['source'] == '高德地图' and s['image'] for s in r['spots'])
        c.get('/api/discover/spots', params={'city':'杭州'})
        assert len(calls) == len(PLACES['杭州'])
        monkeypatch.delenv('AMAP_API_KEY',raising=False)
        assert not c.get('/api/discover/spots', params={'city':'未收录城市'}).json()['spots']
    discover._cache.clear()

def test_permission_failure_is_explicit_domestic_fallback(monkeypatch):
    discover._cache.clear()
    monkeypatch.setenv('AMAP_API_KEY', 'test-only')
    async def query(*args): return None, '10009'
    monkeypatch.setattr(discover, 'query_amap', query)
    with TestClient(app) as c:
        r = c.get('/api/discover/spots',params={'city':'南京'}).json()
    assert r['mode'] == 'mock' and r['errors'] == ['10009']
    assert all(s['source'] == '本地示例' and not s['image'] for s in r['spots'])
    discover._cache.clear()
