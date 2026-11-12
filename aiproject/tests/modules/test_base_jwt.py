"""BASE RS256 core. Temporary in-memory keys; no database and no customer writes."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security.base_jwt import (
    ACCESS_TOKEN_USE,
    ISSUER,
    SERVICE_TOKEN_USE,
    BaseKeyConfigError,
    BaseKeySet,
    BaseTokenError,
    issue_access_token,
    issue_service_token,
    jwks_document,
    keyset_from_config,
    load_keyset,
    verify_token,
)
from app.core.security.credentials import decode_token, issue_token
from app.main import app

SID = "11111111-1111-4111-8111-111111111111"
PRIVATE_FIELDS = ("d", "p", "q", "dp", "dq", "qi", "oth")


def _pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _entry(kid: str, status: str, private_pem: str, public_pem: str) -> dict:
    item = {"kid": kid, "status": status, "public_pem": public_pem}
    if status == "active":
        item["private_pem"] = private_pem
    return item


def _keyset(*entries: dict) -> BaseKeySet:
    return keyset_from_config(list(entries))


@pytest.fixture()
def keys():
    current = _pair()
    previous = _pair()
    return current, previous


def _active(keys) -> BaseKeySet:
    private_pem, public_pem = keys[0]
    return _keyset(_entry("base-current", "active", private_pem, public_pem))


def _issue(keys, **overrides) -> str:
    values = {
        "sub": "42",
        "sid": SID,
        "audience": "edu-api:ent",
        "user_type": "employee",
        "ttl_seconds": 600,
    }
    values.update(overrides)
    return issue_access_token(_active(keys), **values)


def test_valid_rs256_token(keys):
    token = _issue(keys)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == "base-current"
    assert header["typ"] == "JWT"
    claims = verify_token(
        _active(keys), token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE
    )
    assert claims["iss"] == ISSUER
    assert claims["aud"] == "edu-api:ent"
    assert claims["sub"] == "42"
    assert claims["sid"] == SID
    assert claims["user_type"] == "employee"
    assert claims["token_use"] == ACCESS_TOKEN_USE
    assert claims["nbf"] == claims["iat"]
    assert claims["exp"] - claims["iat"] == 600


def test_bad_signature_is_rejected(keys):
    token = _issue(keys)
    other_private, other_public = keys[1]
    other = _keyset(_entry("base-current", "active", other_private, other_public))
    with pytest.raises(BaseTokenError):
        verify_token(other, token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE)


def test_wrong_issuer_is_rejected(keys):
    private_pem, public_pem = keys[0]
    token = jwt.encode(
        {
            "iss": "ent-portal",
            "aud": "edu-api:ent",
            "sub": "42",
            "sid": SID,
            "user_type": "employee",
            "token_use": ACCESS_TOKEN_USE,
            "iat": int(time.time()),
            "nbf": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "base-current", "typ": "JWT"},
    )
    keyset = _keyset(_entry("base-current", "active", private_pem, public_pem))
    with pytest.raises(BaseTokenError):
        verify_token(keyset, token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE)


def test_wrong_audience_is_rejected(keys):
    token = _issue(keys)
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), token, audience="edu-api:stu", token_use=ACCESS_TOKEN_USE
        )


def test_expired_token_is_rejected(keys):
    token = _issue(keys, now=datetime.now(timezone.utc) - timedelta(hours=2), ttl_seconds=60)
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE
        )


def test_not_yet_valid_token_is_rejected(keys):
    token = _issue(keys, now=datetime.now(timezone.utc) + timedelta(minutes=10))
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE
        )


def test_unknown_and_disabled_kid_are_rejected(keys):
    token = _issue(keys)
    private_pem, public_pem = keys[0]
    disabled = _keyset(_entry("base-current", "disabled", private_pem, public_pem))
    with pytest.raises(BaseTokenError):
        verify_token(disabled, token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE)
    renamed = jwt.encode(
        jwt.decode(token, options={"verify_signature": False}),
        private_pem,
        algorithm="RS256",
        headers={"kid": "missing-kid", "typ": "JWT"},
    )
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), renamed, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE
        )


def test_hs256_token_is_rejected(keys):
    token = jwt.encode(
        {"sub": "42", "sid": SID},
        "x" * 32,
        algorithm="HS256",
        headers={"kid": "base-current", "typ": "JWT"},
    )
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE
        )
    none_token = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIiwia2lkIjoiYmFzZS1jdXJyZW50In0.eyJzdWIiOiI0MiJ9."
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), none_token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE
        )


def test_wrong_token_use_is_rejected(keys):
    token = issue_service_token(
        _active(keys),
        sub="svc:report-bot",
        sid=SID,
        audience="edu-api:rpt",
        ttl_seconds=300,
    )
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), token, audience="edu-api:rpt", token_use=ACCESS_TOKEN_USE
        )
    access = _issue(keys)
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), access, audience="edu-api:ent", token_use=SERVICE_TOKEN_USE
        )


def test_jwks_contains_only_public_material(keys):
    current_private, current_public = keys[0]
    previous_private, previous_public = keys[1]
    keyset = _keyset(
        _entry("base-current", "active", current_private, current_public),
        _entry("base-previous", "verify_only", previous_private, previous_public),
        _entry("base-retired", "disabled", current_private, current_public),
    )
    document = jwks_document(keyset)
    kids = [item["kid"] for item in document["keys"]]
    assert kids == ["base-current", "base-previous"]
    encoded = json.dumps(document)
    assert "PRIVATE" not in encoded
    assert current_private not in encoded
    for item in document["keys"]:
        assert item["alg"] == "RS256"
        assert item["use"] == "sig"
        for field in PRIVATE_FIELDS:
            assert field not in item


def test_missing_key_config_fails_closed(monkeypatch):
    monkeypatch.delenv("BASE_JWT_KEYS", raising=False)
    monkeypatch.delenv("BASE_JWT_KEYS_FILE", raising=False)
    with pytest.raises(BaseKeyConfigError):
        load_keyset()
    client = TestClient(app)
    response = client.get("/api/v1/auth/jwks")
    assert response.status_code == 503
    assert response.json()["detail"] == "BASE 公钥未就绪"
    assert response.headers["cache-control"] == "no-store"
    assert "keys" not in response.json()


def test_multiple_kids_verify_and_rotate(keys, monkeypatch):
    current_private, current_public = keys[0]
    previous_private, previous_public = keys[1]
    old_signer = _keyset(
        _entry("base-previous", "active", previous_private, previous_public)
    )
    old_token = issue_access_token(
        old_signer,
        sub="7",
        sid=SID,
        audience="edu-api:pf",
        user_type="admin",
        ttl_seconds=900,
    )
    rotated = _keyset(
        _entry("base-current", "active", current_private, current_public),
        _entry("base-previous", "verify_only", previous_private, previous_public),
    )
    old_claims = verify_token(
        rotated, old_token, audience="edu-api:pf", token_use=ACCESS_TOKEN_USE
    )
    assert old_claims["user_type"] == "admin"
    new_token = issue_access_token(
        rotated,
        sub="8",
        sid=SID,
        audience="edu-api:cs",
        user_type="student",
        ttl_seconds=900,
    )
    assert jwt.get_unverified_header(new_token)["kid"] == "base-current"
    assert verify_token(
        rotated, new_token, audience="edu-api:cs", token_use=ACCESS_TOKEN_USE
    )["sub"] == "8"
    with pytest.raises(BaseKeyConfigError):
        issue_access_token(
            _keyset(_entry("base-previous", "verify_only", previous_private, previous_public)),
            sub="8",
            sid=SID,
            audience="edu-api:cs",
            user_type="student",
        )
    monkeypatch.setenv(
        "BASE_JWT_KEYS",
        json.dumps([
            _entry("base-current", "active", current_private, current_public),
            _entry("base-previous", "verify_only", previous_private, previous_public),
        ]),
    )
    response = TestClient(app).get("/api/v1/auth/jwks")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=60"
    assert [item["kid"] for item in response.json()["keys"]] == [
        "base-current",
        "base-previous",
    ]


def test_ent_portal_hs256_remains_unchanged(keys):
    settings = Settings(
        _env_file=None,
        employee_identity_mode="trusted_jwt",
        auth_jwt_secret="portal-test-secret-value-32chars",
    )
    token, sid, _exp = issue_token(42, settings)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "HS256"
    assert "kid" not in header
    claims = decode_token(token, settings)
    assert claims["iss"] == "ent-portal"
    assert claims["aud"] == "ent-api"
    assert claims["typ"] == "access"
    assert claims["sub"] == "42"
    assert claims["sid"] == sid
    with pytest.raises(BaseTokenError):
        verify_token(
            _active(keys), token, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE
        )


def test_service_token_omits_user_type(keys):
    token = issue_service_token(
        _active(keys),
        sub="svc:report-bot",
        sid=SID,
        audience="edu-auth:token-exchange",
    )
    claims = verify_token(
        _active(keys),
        token,
        audience="edu-auth:token-exchange",
        token_use=SERVICE_TOKEN_USE,
    )
    assert "user_type" not in claims
    assert claims["sub"] == "svc:report-bot"
