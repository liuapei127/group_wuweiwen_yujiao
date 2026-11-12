from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "education_service"
    db_user: str = "root"
    db_password: str = ""
    upload_dir: str = "/uploads"
    # 本地/联调用服务间 Bearer（.env 配置，勿提交）。不等同于员工身份。
    auth_bearer_token: str = ""
    # blocked | trusted_jwt（后者需完整JWT及认证表配置）。漏洞复现见 tests/repro/asgi_app，不设此开关。
    employee_identity_mode: str = "blocked"

    # Portal login is enabled explicitly for its process, not by trusting headers.
    auth_jwt_secret: SecretStr = SecretStr('')
    auth_jwt_issuer: str = 'ent-portal'
    auth_jwt_audience: str = 'ent-api'
    auth_access_minutes: int = Field(default=60,ge=5,le=1440)
    dify_api_url: str = 'http://127.0.0.1:8088/v1'
    dify_workflow_api_key: SecretStr = SecretStr('')
    dify_timeout_seconds: int = Field(default=45,ge=5,le=120)
    assistant_api_url: str = 'http://127.0.0.1:8002'

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
