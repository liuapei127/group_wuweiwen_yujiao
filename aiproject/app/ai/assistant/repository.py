import json
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select,insert,update,or_
from app.core.security.credentials import utc_now
from .models import conversations,messages

class AssistantRepository:
    def __init__(self,db):self.db=db

    def create(self,user_id,title):
        cid=str(uuid4())
        self.db.execute(insert(conversations).values(id=cid,employee_id=user_id,title=title,pending='',version=0,create_time=utc_now(),update_time=utc_now()))
        return cid

    def get(self,cid,user_id):
        r=self.db.execute(select(conversations).where(conversations.c.id==cid,conversations.c.employee_id==user_id)).mappings().first()
        return dict(r) if r else None

    def list(self,user_id):
        return [dict(r) for r in self.db.execute(select(conversations.c.id,conversations.c.title,conversations.c.version,conversations.c.update_time).where(
            conversations.c.employee_id==user_id).order_by(conversations.c.update_time.desc()).limit(100)).mappings()]

    def history(self,cid):
        rows=[dict(r) for r in self.db.execute(select(messages).where(messages.c.conversation_id==cid).order_by(messages.c.id.desc()).limit(100)).mappings()]
        for r in rows:r['metadata']=json.loads(r.pop('metadata_json'))
        return list(reversed(rows))

    def reserve(self,cid,user_id,version):
        nonce=str(uuid4());now=utc_now()
        # CAS reserves a turn and clears pending BEFORE any network or write call.
        count=self.db.execute(update(conversations).where(conversations.c.id==cid,conversations.c.employee_id==user_id,
            conversations.c.version==version,or_(conversations.c.busy_token.is_(None),conversations.c.busy_until<now)).values(
                version=version+1,busy_token=nonce,busy_until=now+timedelta(seconds=180),pending='',update_time=now)).rowcount
        return nonce if count==1 else None

    def finish(self,cid,user_id,version,nonce,pending,text,reply,metadata):
        count=self.db.execute(update(conversations).where(conversations.c.id==cid,conversations.c.employee_id==user_id,
            conversations.c.version==version,conversations.c.busy_token==nonce).values(
                pending=pending,busy_token=None,busy_until=None,update_time=utc_now(),title=text[:60] if version==1 else conversations.c.title)).rowcount
        if count!=1:return False
        self.db.execute(insert(messages),[
            {'conversation_id':cid,'role':'user','content':text,'metadata_json':'{}','create_time':utc_now()},
            {'conversation_id':cid,'role':'assistant','content':reply,'metadata_json':json.dumps(metadata,ensure_ascii=False,default=str),'create_time':utc_now()}])
        return True
