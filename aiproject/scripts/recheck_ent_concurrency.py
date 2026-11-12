"""Persist every consecutive isolated-database regression run; stop on any failure."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--repeats',type=int,default=5);a=p.parse_args()
results=[]
for i in range(a.repeats):
 proc=subprocess.run([sys.executable,'-X','utf8','-m','scripts.verify_ent_concurrency','--database',a.database],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
 result={'round':i+1,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}
 results.append(result)
 (ROOT/'docs/回复Cursor/runs/ent-repair-concurrency-consecutive.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
 latest=ROOT/'docs/回复Cursor/runs/ent-mysql-concurrency.json'
 (ROOT/f'docs/回复Cursor/runs/ent-repair-concurrency-round-{i+1}.json').write_bytes(latest.read_bytes())
 print(json.dumps({'round':i+1,'exit_code':proc.returncode},ensure_ascii=False),flush=True)
 if proc.returncode:raise SystemExit(proc.returncode)
