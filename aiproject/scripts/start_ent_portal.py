"""Start the authenticated local portal without changing the existing blocked API."""
import argparse,json,os,shutil,socket,subprocess,sys,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'logs/ent-portal-processes.json'
API='http://127.0.0.1:8002'
WEB='http://127.0.0.1:5173'


def occupied(port):
    with socket.socket() as sock:return sock.connect_ex(('127.0.0.1',port))==0


def wait(url):
    deadline=time.monotonic()+25
    with httpx.Client(trust_env=False,timeout=2) as client:
        while time.monotonic()<deadline:
            try:
                if client.get(url).status_code==200:return
            except httpx.HTTPError:pass
            time.sleep(.3)
    raise RuntimeError('Startup timed out: '+url+'; inspect logs/ent-portal-api.log and ent-portal-web.log')


def stop_owned(state):
    if state.get('project')!=str(ROOT):raise RuntimeError('Process state belongs to another workspace')
    for key,port,marker in [('api',8002,'app.main:app'),('web',5173,'vite')]:
        pid=state.get(key+'_pid')
        if not pid:continue
        result=subprocess.run(['wmic','process','where','ProcessId='+str(int(pid)),'get','CommandLine'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        command=result.stdout
        if marker not in command or str(port) not in command:continue
        if key=='web' and str(ROOT/'frontend') not in command.replace('\\','/') and str(ROOT/'frontend').replace('\\','/') not in command.replace('\\','/'):
            raise RuntimeError('Refusing to stop an unrelated web process')
        subprocess.run(['taskkill','/PID',str(int(pid)),'/T','/F'],capture_output=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--restart',action='store_true');parser.add_argument('--production',action='store_true');args=parser.parse_args()
    (ROOT/'logs').mkdir(exist_ok=True)
    if args.restart and STATE.exists():stop_owned(json.loads(STATE.read_text(encoding='utf-8')));time.sleep(.5)
    state={'project':str(ROOT),'api_url':API,'frontend_url':WEB}
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    if not occupied(8002):
        env=os.environ.copy();env.update(EMPLOYEE_IDENTITY_MODE='trusted_jwt',ASSISTANT_API_URL=API,PYTHONUTF8='1')
        log=open(ROOT/'logs/ent-portal-api.log','a',encoding='utf-8')
        proc=subprocess.Popen([str(ROOT/'.venv313/Scripts/python.exe'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8002'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        state['api_pid']=proc.pid
    wait(API+'/api/v1/auth/status')
    with httpx.Client(trust_env=False,timeout=5) as client:
        status=client.get(API+'/api/v1/auth/status').json().get('data',{})
        if not status.get('ready'):raise RuntimeError('Portal authentication is not initialized; run scripts.setup_ent_portal --bootstrap first')
    if not occupied(5173):
        node=shutil.which('node')
        if not node:raise RuntimeError('Node.js is required')
        cmd=[node,str(ROOT/'frontend/node_modules/vite/bin/vite.js')]
        if args.production:cmd+=['preview']
        cmd+=['--host','127.0.0.1','--port','5173','--strictPort']
        log=open(ROOT/'logs/ent-portal-web.log','a',encoding='utf-8')
        proc=subprocess.Popen(cmd,cwd=ROOT/'frontend',stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        state['web_pid']=proc.pid
    wait(WEB)
    if STATE.exists():
        old=json.loads(STATE.read_text(encoding='utf-8'))
        for k in ('api_pid','web_pid'):
            if k not in state and old.get('project')==str(ROOT):state[k]=old.get(k)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(state,ensure_ascii=False))

if __name__=='__main__':main()
