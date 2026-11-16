"""Password hashing and strictly scoped JWTs; secrets never enter a model prompt."""
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from pwdlib import PasswordHash
from jwt import InvalidTokenError
from fastapi import HTTPException

from app.core.exceptions import BusinessError
from app.shared.types.phone import MOBILE_PATTERN

password_hasher = PasswordHash.recommended()
_DUMMY_HASH = password_hasher.hash('dummy-password-for-timing-only')


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password):
    return password_hasher.hash(password)


def password_for_reset(username: str, requested: str | None) -> str:
    if not re.fullmatch(MOBILE_PATTERN, username):
        raise BusinessError(422, "请先将登录账号迁移为手机号")
    if requested is not None:
        raise BusinessError(422, "密码自动重置为 YJ 加手机号后 6 位")
    return "YJ" + username[-6:]


def verify_password(password, hashed):
    try:
        return password_hasher.verify(password, hashed or _DUMMY_HASH)
    except (ValueError, TypeError):
        password_hasher.verify(password, _DUMMY_HASH)
        return False
    except Exception as exc:
        # Unsupported legacy placeholder hashes must fail closed too.
        if type(exc).__module__.startswith(('pwdlib','argon2')):
            password_hasher.verify(password, _DUMMY_HASH)
            return False
        raise


def require_auth_config(settings):
    if settings.employee_identity_mode != 'trusted_jwt':
        raise HTTPException(503, '员工可信身份未启用')
    secret = settings.auth_jwt_secret.get_secret_value()
    if len(secret) < 32:
        raise HTTPException(503, '服务端身份签名配置未就绪')
    return secret


def issue_token(user_id, settings):
    secret = require_auth_config(settings)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.auth_access_minutes)
    sid = str(uuid4())
    claims = {'sub':str(user_id),'sid':sid,'iat':now,'nbf':now,'exp':expires,
              'iss':settings.auth_jwt_issuer,'aud':settings.auth_jwt_audience,'typ':'access'}
    token = jwt.encode(claims, secret, algorithm='HS256')
    return token, sid, expires.replace(tzinfo=None)


def decode_token(token, settings):
    secret = require_auth_config(settings)
    try:
        claims = jwt.decode(token,secret,algorithms=['HS256'],issuer=settings.auth_jwt_issuer,
                            audience=settings.auth_jwt_audience,
                            options={'require':['sub','sid','iat','nbf','exp','iss','aud','typ']})
        if claims['typ'] != 'access' or not claims['sub'].isdigit() or int(claims['sub']) < 1:
            raise InvalidTokenError('Invalid subject')
        if not isinstance(claims['sid'],str) or len(claims['sid']) != 36:
            raise InvalidTokenError('Invalid session')
        return claims
    except (InvalidTokenError,ValueError,TypeError,KeyError,AttributeError):
        raise HTTPException(401, '登录已失效，请重新登录', headers={'WWW-Authenticate':'Bearer'}) from None
