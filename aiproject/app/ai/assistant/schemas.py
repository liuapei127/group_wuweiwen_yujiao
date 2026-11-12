from pydantic import BaseModel,ConfigDict,Field
class ConversationCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(default='新对话',min_length=1,max_length=128)
class MessageInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=8000)
    expected_version:int=Field(ge=0)
