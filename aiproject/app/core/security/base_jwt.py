"""BASE RS256 access tokens. Independent of the ENT portal HS256 verifier."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from jwt.algorithms import RSAAlgorithm

ISSUER = "edu-base"
RESOURCE_AUDIENCES = frozenset({
    "edu-api:ent",
    "edu-api:pf",
    "edu-api:cs",
    "edu-api:stu",
    "edu-api:rpt",
})
# Named by the implementation-detail note for a future exchange call.
# No exchange route is registered in this phase.
SERVICE_EXCHANGE_AUDIENCE = "edu-auth:token-exchange"
ACCESS_TOKEN_USE = "access"
SERVICE_TOKEN_USE = "service_access"
USER_TYPES = frozenset({"employee", "admin", "student"})
MAX_TTL_SECONDS = 60 * 60
_KID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_USER_SUB = re.compile(r"[1-9][0-9]*")
_SERVICE_SUB = re.compile(r"svc:[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_SID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
_PRIVATE_JWK_FIELDS = ("d", "p", "q", "dp", "dq", "qi", "oth")


class BaseTokenError(Exception):
    """A token or claim set is not acceptable."""


class BaseKeyConfigError(BaseTokenError):
    """Signing or verification keys are missing or unsafe."""


@dataclass(frozen=True)
class BaseKey:
    kid: str
    status: str
    public_pem: str
    private_pem: str | None


class BaseKeySet:
    def __init__(self, keys: list[BaseKey]):
        if not keys:
            raise BaseKeyConfigError("BASE 密钥未配置")
        seen: set[str] = set()
        active: list[BaseKey] = []
        verifiable: dict[str, BaseKey] = {}
        for key in keys:
            if key.kid in seen:
                raise BaseKeyConfigError("BASE kid 重复")
            seen.add(key.kid)
            if key.status == "active":
                active.append(key)
                verifiable[key.kid] = key
            elif key.status == "verify_only":
                verifiable[key.kid] = key
            elif key.status != "disabled":
                raise BaseKeyConfigError("BASE 密钥状态无效")
        if len(active) > 1:
            raise BaseKeyConfigError("BASE 同时只能有一把签发密钥")
        self._keys = tuple(keys)
        self._active = active[0] if active else None
        self._verifiable = verifiable

    @property
    def keys(self) -> tuple[BaseKey, ...]:
        return self._keys

    def signing_key(self) -> BaseKey:
        if self._active is None or not self._active.private_pem:
            raise BaseKeyConfigError("BASE 签发密钥未配置")
        return self._active

    def verification_key(self, kid: str) -> BaseKey:
        key = self._verifiable.get(kid)
        if key is None:
            raise BaseTokenError("BASE 令牌无效")
        return key


def load_keyset() -> BaseKeySet:
    raw = _read_key_config()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BaseKeyConfigError("BASE 密钥配置无效") from exc
    return keyset_from_config(parsed)


def keyset_from_config(parsed: object) -> BaseKeySet:
    if not isinstance(parsed, list):
        raise BaseKeyConfigError("BASE 密钥配置无效")
    return BaseKeySet([_parse_key(item) for item in parsed])


def issue_access_token(
    keyset: BaseKeySet,
    *,
    sub: str,
    sid: str,
    audience: str,
    user_type: str,
    ttl_seconds: int = MAX_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    if user_type not in USER_TYPES:
        raise BaseTokenError("BASE 令牌声明无效")
    if not isinstance(sub, str) or _USER_SUB.fullmatch(sub) is None:
        raise BaseTokenError("BASE 令牌声明无效")
    if audience not in RESOURCE_AUDIENCES:
        raise BaseTokenError("BASE 令牌声明无效")
    return _issue(
        keyset,
        sub=sub,
        sid=sid,
        audience=audience,
        token_use=ACCESS_TOKEN_USE,
        user_type=user_type,
        ttl_seconds=ttl_seconds,
        now=now,
    )


def issue_service_token(
    keyset: BaseKeySet,
    *,
    sub: str,
    sid: str,
    audience: str,
    ttl_seconds: int = MAX_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    if not isinstance(sub, str) or _SERVICE_SUB.fullmatch(sub) is None:
        raise BaseTokenError("BASE 令牌声明无效")
    allowed = RESOURCE_AUDIENCES | {SERVICE_EXCHANGE_AUDIENCE}
    if audience not in allowed:
        raise BaseTokenError("BASE 令牌声明无效")
    return _issue(
        keyset,
        sub=sub,
        sid=sid,
        audience=audience,
        token_use=SERVICE_TOKEN_USE,
        user_type=None,
        ttl_seconds=ttl_seconds,
        now=now,
    )


def verify_token(
    keyset: BaseKeySet,
    token: str,
    *,
    audience: str,
    token_use: str,
) -> dict:
    if token_use not in {ACCESS_TOKEN_USE, SERVICE_TOKEN_USE}:
        raise BaseTokenError("BASE 令牌无效")
    if not isinstance(token, str) or token.count(".") != 2:
        raise BaseTokenError("BASE 令牌无效")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise BaseTokenError("BASE 令牌无效") from exc
    if header.get("alg") != "RS256" or header.get("typ") != "JWT":
        raise BaseTokenError("BASE 令牌无效")
    kid = header.get("kid")
    if not isinstance(kid, str):
        raise BaseTokenError("BASE 令牌无效")
    key = keyset.verification_key(kid)
    try:
        claims = jwt.decode(
            token,
            key.public_pem,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=audience,
            leeway=0,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "sid", "token_use"]},
        )
    except jwt.PyJWTError as exc:
        raise BaseTokenError("BASE 令牌无效") from exc
    _check_claims(claims, token_use)
    return claims


def jwks_document(keyset: BaseKeySet) -> dict:
    published = [key for key in keyset.keys if key.status in {"active", "verify_only"}]
    if not published:
        raise BaseKeyConfigError("BASE 公钥未配置")
    return {"keys": [_public_jwk(key) for key in published]}


def _issue(
    keyset: BaseKeySet,
    *,
    sub: str,
    sid: str,
    audience: str,
    token_use: str,
    user_type: str | None,
    ttl_seconds: int,
    now: datetime | None,
) -> str:
    if not isinstance(sid, str) or _SID.fullmatch(sid) is None:
        raise BaseTokenError("BASE 令牌声明无效")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise BaseTokenError("BASE 令牌声明无效")
    if ttl_seconds < 1 or ttl_seconds > MAX_TTL_SECONDS:
        raise BaseTokenError("BASE 令牌声明无效")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise BaseTokenError("BASE 令牌声明无效")
    issued = int(moment.timestamp())
    payload: dict = {
        "iss": ISSUER,
        "aud": audience,
        "sub": sub,
        "sid": sid,
        "token_use": token_use,
        "iat": issued,
        "nbf": issued,
        "exp": issued + ttl_seconds,
    }
    if user_type is not None:
        payload["user_type"] = user_type
    key = keyset.signing_key()
    return jwt.encode(
        payload,
        key.private_pem,
        algorithm="RS256",
        headers={"kid": key.kid, "typ": "JWT"},
    )


def _check_claims(claims: dict, token_use: str) -> None:
    if claims.get("iss") != ISSUER or claims.get("token_use") != token_use:
        raise BaseTokenError("BASE 令牌无效")
    if isinstance(claims.get("aud"), list):
        raise BaseTokenError("BASE 令牌无效")
    iat = _numeric_date(claims.get("iat"))
    nbf = _numeric_date(claims.get("nbf"))
    exp = _numeric_date(claims.get("exp"))
    if nbf < iat or exp <= nbf or exp - iat > MAX_TTL_SECONDS:
        raise BaseTokenError("BASE 令牌无效")
    sid = claims.get("sid")
    if not isinstance(sid, str) or _SID.fullmatch(sid) is None:
        raise BaseTokenError("BASE 令牌无效")
    sub = claims.get("sub")
    if token_use == ACCESS_TOKEN_USE:
        if claims.get("user_type") not in USER_TYPES:
            raise BaseTokenError("BASE 令牌无效")
        if not isinstance(sub, str) or _USER_SUB.fullmatch(sub) is None:
            raise BaseTokenError("BASE 令牌无效")
        return
    if "user_type" in claims:
        raise BaseTokenError("BASE 令牌无效")
    if not isinstance(sub, str) or _SERVICE_SUB.fullmatch(sub) is None:
        raise BaseTokenError("BASE 令牌无效")


def _numeric_date(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BaseTokenError("BASE 令牌无效")
    return value


def _read_key_config() -> str:
    file_name = os.getenv("BASE_JWT_KEYS_FILE", "").strip()
    if file_name:
        path = Path(file_name)
        if not path.is_file():
            raise BaseKeyConfigError("BASE 密钥未配置")
        return path.read_text(encoding="utf-8")
    raw = os.getenv("BASE_JWT_KEYS")
    if raw is None or not raw.strip():
        raise BaseKeyConfigError("BASE 密钥未配置")
    return raw


def _parse_key(item: object) -> BaseKey:
    if not isinstance(item, dict):
        raise BaseKeyConfigError("BASE 密钥配置无效")
    kid = item.get("kid")
    status = item.get("status")
    public_pem = item.get("public_pem")
    private_pem = item.get("private_pem")
    if not isinstance(kid, str) or _KID.fullmatch(kid) is None:
        raise BaseKeyConfigError("BASE 密钥配置无效")
    if status not in {"active", "verify_only", "disabled"}:
        raise BaseKeyConfigError("BASE 密钥配置无效")
    if not isinstance(public_pem, str):
        raise BaseKeyConfigError("BASE 密钥配置无效")
    if private_pem is not None and not isinstance(private_pem, str):
        raise BaseKeyConfigError("BASE 密钥配置无效")
    if status == "active" and not private_pem:
        raise BaseKeyConfigError("BASE 签发密钥未配置")
    if status != "active" and private_pem:
        raise BaseKeyConfigError("BASE 停用密钥不能保留私钥")
    public_key = _public_key(public_pem)
    if private_pem:
        private_key = _private_key(private_pem)
        if private_key.public_key().public_numbers() != public_key.public_numbers():
            raise BaseKeyConfigError("BASE 密钥配置无效")
    return BaseKey(kid=kid, status=status, public_pem=public_pem, private_pem=private_pem)


def _public_jwk(key: BaseKey) -> dict:
    public = json.loads(RSAAlgorithm.to_jwk(_public_key(key.public_pem)))
    for field in _PRIVATE_JWK_FIELDS:
        public.pop(field, None)
    public["kid"] = key.kid
    public["use"] = "sig"
    public["alg"] = "RS256"
    return public


def _public_key(pem: str):
    try:
        key = load_pem_public_key(pem.encode("utf-8"))
    except ValueError as exc:
        raise BaseKeyConfigError("BASE 密钥配置无效") from exc
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
        raise BaseKeyConfigError("BASE 密钥配置无效")
    return key


def _private_key(pem: str):
    try:
        key = load_pem_private_key(pem.encode("utf-8"), password=None)
    except (TypeError, ValueError) as exc:
        raise BaseKeyConfigError("BASE 密钥配置无效") from exc
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise BaseKeyConfigError("BASE 密钥配置无效")
    return key
