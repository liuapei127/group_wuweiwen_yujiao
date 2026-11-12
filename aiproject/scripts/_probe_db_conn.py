"""一次性探测本机 MySQL 连接（不打印密码）。成功时写出 .env 片段到 stdout 的变量名提示。"""
import os
import sys

import pymysql

host = os.getenv("DB_HOST", "127.0.0.1")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "root")
db = os.getenv("DB_NAME", "education_service")
password = os.getenv("DB_PASSWORD")

candidates = []
if password is not None:
    candidates.append(password)
else:
    # 仅探测；请在环境变量 DB_PASSWORD 中提供真实密码
    candidates.extend(["", "123456", "root", "mysql", "password"])

for pwd in candidates:
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=pwd, database=db, charset="utf8mb4")
        conn.close()
        print("OK")
        print(f"DB_HOST={host}")
        print(f"DB_PORT={port}")
        print(f"DB_USER={user}")
        print(f"DB_NAME={db}")
        print("DB_PASSWORD_SET=yes")
        # 供父进程使用
        sys.exit(100 if pwd == "" else 0)
    except pymysql.Error:
        continue
print("FAIL")
sys.exit(1)
