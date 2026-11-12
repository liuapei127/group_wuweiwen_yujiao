from uuid import UUID
from fastapi import APIRouter,Depends,Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import EmployeePrincipal,require_employee
from app.core.responses import success
from .schemas import ConversationCreate,MessageInput
from .service import AssistantService
router=APIRouter(prefix='/api/v1/ai/assistant',tags=['AI业务助手'])

@router.get('/conversations')
def conversations(db:Session=Depends(get_db),p:EmployeePrincipal=Depends(require_employee)):
    return success(AssistantService(db).list(p))

@router.post('/conversations')
def create(body:ConversationCreate,db:Session=Depends(get_db),p:EmployeePrincipal=Depends(require_employee)):
    return success(AssistantService(db).create(body,p))

@router.get('/conversations/{conversation_id}')
def detail(conversation_id:UUID,db:Session=Depends(get_db),p:EmployeePrincipal=Depends(require_employee)):
    return success(AssistantService(db).detail(str(conversation_id),p))

@router.post('/conversations/{conversation_id}/messages')
def message(conversation_id:UUID,body:MessageInput,request:Request,db:Session=Depends(get_db),p:EmployeePrincipal=Depends(require_employee)):
    # Only forwarded to this same backend's fixed loopback API, never to Dify.
    token=request.headers.get('Authorization','').split(' ',1)[1]
    return success(AssistantService(db).send(str(conversation_id),body,p,token))
