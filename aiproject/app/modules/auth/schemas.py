from pydantic import BaseModel, ConfigDict, Field, SecretStr

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Login(Input):
    username: str = Field(min_length=1,max_length=64)
    password: str = Field(min_length=1,max_length=256)

class PasswordChange(Input):
    old_password: str = Field(min_length=1,max_length=256)
    new_password: str = Field(min_length=12,max_length=128)

class PasswordReset(Input):
    new_password: str = Field(min_length=12,max_length=128)

class UserCreate(Input):
    username: str = Field(min_length=3,max_length=64,pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=12,max_length=128)
    real_name: str = Field(min_length=1,max_length=64)
    role_id: int = Field(gt=0)
    department: str | None = Field(default=None,max_length=128)
    contact_info: str | None = Field(default=None,max_length=128)
    status: str = Field(default='normal',pattern=r'^(normal|disabled)$')

class UserUpdate(Input):
    real_name: str = Field(min_length=1,max_length=64)
    role_id: int = Field(gt=0)
    department: str | None = Field(default=None,max_length=128)
    contact_info: str | None = Field(default=None,max_length=128)
    status: str = Field(pattern=r'^(normal|disabled)$')

class RoleWrite(Input):
    role_code: str = Field(min_length=2,max_length=32,pattern=r'^[a-z][a-z0-9_]+$')
    role_name: str = Field(min_length=1,max_length=64)
    description: str | None = Field(default=None,max_length=255)
    status: int = Field(default=1,ge=0,le=1)
    permissions: list[str] = Field(default_factory=list,max_length=100)

class StudentScope(Input):
    student_ids: list[int] = Field(default_factory=list,max_length=10000)


class ServiceTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1, max_length=64)
    client_secret: SecretStr
    audience: str = Field(min_length=1, max_length=64)
