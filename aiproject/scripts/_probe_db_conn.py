"""一次性探测本机 MySQL 连接（不打印密码）。成功时只提示变量名。"""
import os
import sys
from pathlib import Path

import pymysql

host = os.getenv("DB_HOST", "127.0.0.1")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "root")
db = os.getenv("DB_NAME", "education_service")


def resolve_password():
    if os.getenv("DB_PASSWORD") is not None:
        return os.getenv("DB_PASSWORD")
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DB_PASSWORD="):
                return line.split("=", 1)[1].strip()
    return None


password = resolve_password()
if password is None:
    print("FAIL")
    sys.exit(1)
try:
    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db, charset="utf8mb4")
    conn.close()
except pymysql.Error:
    print("FAIL")
    sys.exit(1)
print("OK")
print(f"DB_HOST={host}")
print(f"DB_PORT={port}")
print(f"DB_USER={user}")
print(f"DB_NAME={db}")
print("DB_PASSWORD_SET=yes")
sys.exit(100 if password == "" else 0)
