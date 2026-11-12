"""Back up only the local Dify application database; never print dump contents."""
import hashlib,json,subprocess
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'logs'/('dify-before-repair-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True,exist_ok=False)
dump=out/'dify.pgdump'
with dump.open('wb') as target:
 result=subprocess.run(['docker','exec','-u','postgres','dify-db_postgres-1','pg_dump','-Fc','dify'],stdout=target,stderr=subprocess.PIPE,timeout=90)
if result.returncode:raise RuntimeError(result.stderr.decode('utf-8',errors='replace'))
assert dump.stat().st_size>0
print(json.dumps({'backup':str(dump),'bytes':dump.stat().st_size,'sha256':hashlib.sha256(dump.read_bytes()).hexdigest()}))
