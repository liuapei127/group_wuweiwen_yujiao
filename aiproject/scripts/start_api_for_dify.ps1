# 供本机 Dify（Docker）调用的 FastAPI：监听 0.0.0.0:8000
# Dify HTTP 节点 Base URL: http://host.docker.internal:8000

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root ".venv313\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "未找到 .venv313，请先: py -3.13 -m venv .venv313; pip install -e ."
    exit 1
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Write-Host "请复制 .env.example -> .env 并填写 DB_*"
    exit 1
}

Write-Host "启动 app.main -> http://127.0.0.1:8000  (Dify 用 host.docker.internal:8000)"
Write-Host "Swagger: http://127.0.0.1:8000/docs"
Write-Host "说明: 员工业务默认 503；仅 /health 适合 Dify 探活。"
& $Py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
