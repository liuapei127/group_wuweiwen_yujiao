"""Uvicorn 入口：独立 app 工厂，不 import app.main。"""
from tests.repro.factory import create_repro_app

app = create_repro_app()
