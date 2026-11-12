"""Portal contracts under controlled settings and isolated SQLite; never MySQL."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.config import Settings
from app.core.database import Base,get_db,engine as production_engine
from app.core.security import dependencies
from app.modules.auth import service as auth_service
from app.model_registry import register_models
from app.router_registry import register_routers

@pytest.fixture
def isolated_portal(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Portal route test attempted production database access')
    monkeypatch.setattr(production_engine,'connect',forbidden)
    def make(mode='blocked',secret='s'*48,migrated=True):
        settings=Settings(_env_file=None,employee_identity_mode=mode,auth_jwt_secret=secret)
        monkeypatch.setattr(auth_service,'get_settings',lambda:settings)
        monkeypatch.setattr(dependencies,'get_settings',lambda:settings)
        db_engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        if migrated:
            register_models();Base.metadata.create_all(db_engine)
        app=FastAPI();register_routers(app)
        def session():
            with Session(db_engine) as db:yield db
        app.dependency_overrides[get_db]=session
        return app,db_engine
    return make

@pytest.mark.parametrize('mode,secret,migrated,ready',[
    ('blocked','s'*48,True,False),
    ('trusted_jwt','s'*48,True,True),
    ('trusted_jwt','s'*48,False,False),
    ('trusted_jwt','',True,False),
])
def test_auth_status_shape_and_readiness(isolated_portal,mode,secret,migrated,ready):
    app,engine=isolated_portal(mode,secret,migrated)
    try:
        with TestClient(app) as client:
            r=client.get('/api/v1/auth/status')
            assert r.status_code==200
            assert r.json()['code']==0
            assert r.json()['data']=={'mode':mode,'ready':ready}
            assert type(r.json()['data']['ready']) is bool
    finally:engine.dispose()

@pytest.mark.parametrize('mode,expected',[('blocked',503),('trusted_jwt',401)])
def test_portal_context_not_anonymous(isolated_portal,mode,expected):
    app,engine=isolated_portal(mode)
    try:
        with TestClient(app) as client:
            r=client.get('/api/v1/portal/context')
            assert r.status_code==expected
            if expected==401:assert r.headers['www-authenticate']=='Bearer'
    finally:engine.dispose()


def test_invalid_jwt_is_401_without_querying_user_database(isolated_portal):
    app,engine=isolated_portal('trusted_jwt')
    try:
        with TestClient(app) as client:
            assert client.get('/api/v1/portal/context',headers={'Authorization':'Bearer invalid-token'}).status_code==401
    finally:engine.dispose()
