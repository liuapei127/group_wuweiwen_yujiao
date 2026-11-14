from uuid import UUID
from fastapi import APIRouter,Depends,Request,UploadFile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import EmployeePrincipal,require_employee
from app.core.responses import success
from app.modules.employee_report.transcription import MAX_AUDIO_BYTES, transcribe_audio
from .schemas import ConversationCreate,MessageInput
from .service import AssistantService
router=APIRouter(prefix='/api/v1/ai/assistant',tags=['AI业务助手'])

@router.post('/transcribe', summary='录音转写为企业助手消息草稿')
async def transcribe(file: UploadFile, principal: EmployeePrincipal = Depends(require_employee)):
    audio = await file.read(MAX_AUDIO_BYTES + 1)
    return success({"text": await transcribe_audio(audio)})


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
