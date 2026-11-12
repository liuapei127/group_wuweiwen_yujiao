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
        audience="edu-api:rpt",
    )
    claims = verify_token(
        _active(keys),
        token,
        audience="edu-api:rpt",
        token_use=SERVICE_TOKEN_USE,
    )
    assert "user_type" not in claims
    assert claims["sub"] == "svc:report-bot"


def _assert_safe_error(exc: BaseException, private_pem: str) -> None:
    text = str(exc)
    assert text in {"BASE 密钥未配置", "BASE 密钥配置无效", "BASE kid 重复", "BASE 密钥状态无效", "BASE 同时只能有一把签发密钥", "BASE 签发密钥未配置", "BASE 停用密钥不能保留私钥"}
    assert "PRIVATE" not in text
    assert private_pem not in text
    assert exc.__cause__ is None


def test_jwks_http_route(keys, monkeypatch):
    current_private, current_public = keys[0]
    previous_private, previous_public = keys[1]
    monkeypatch.setenv(
        "BASE_JWT_KEYS",
        json.dumps([
            _entry("base-current", "active", current_private, current_public),
            _entry("base-previous", "verify_only", previous_private, previous_public),
            _entry("base-retired", "disabled", current_private, current_public),
        ]),
    )
    paths = app.openapi()["paths"]
    assert list(paths).count("/api/v1/auth/jwks") == 1
    assert set(paths["/api/v1/auth/jwks"]) == {"get"}
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/api/v1/auth/jwks" not in paths
    assert "/api/v1/auth/api/v1/auth/login" not in paths
    client = TestClient(app)
    assert client.get("/api/v1/auth/api/v1/auth/jwks").status_code == 404
    assert client.get("/api/v1/auth/api/v1/auth/login").status_code == 404
    response = client.get("/api/v1/auth/jwks")
    queried = client.get("/api/v1/auth/jwks", params={"audience": "edu-api:stu"})
    assert response.status_code == 200
    assert queried.status_code == 200
    assert response.json() == queried.json()
    assert response.headers["cache-control"] == "public, max-age=60"
    body = response.json()
    assert set(body) == {"keys"}
    kids = [item["kid"] for item in body["keys"]]
    assert kids == ["base-current", "base-previous"]
    encoded = response.text
    assert "PRIVATE" not in encoded
    assert current_private not in encoded
    assert previous_private not in encoded
    for item in body["keys"]:
        assert item["kty"] == "RSA"
        assert item["alg"] == "RS256"
        assert item["use"] == "sig"
        assert "n" in item and "e" in item
        for field in PRIVATE_FIELDS:
            assert field not in item
    monkeypatch.setenv(
        "BASE_JWT_KEYS",
        json.dumps([_entry("base-retired", "disabled", current_private, current_public)]),
    )
    blocked = client.get("/api/v1/auth/jwks")
    assert blocked.status_code == 503
    assert blocked.headers["cache-control"] == "no-store"
    assert blocked.json() == {"detail": "BASE 公钥未就绪"}
    assert current_private not in blocked.text


def test_key_config_boundaries(keys):
    current_private, current_public = keys[0]
    other_private, other_public = keys[1]
    small = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    small_private = small.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    small_public = small.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    cases = [
        [
            _entry("base-current", "active", current_private, current_public),
            _entry("base-current", "verify_only", other_private, other_public),
        ],
        [
            _entry("base-current", "active", current_private, current_public),
            _entry("base-next", "active", other_private, other_public),
        ],
        [{"kid": "base-current", "status": "active", "public_pem": current_public}],
        [{
            "kid": "base-current",
            "status": "verify_only",
            "public_pem": current_public,
            "private_pem": current_private,
        }],
        [{
            "kid": "base-current",
            "status": "disabled",
            "public_pem": current_public,
            "private_pem": current_private,
        }],
        [_entry("base-current", "active", other_private, current_public)],
        [_entry("base-current", "active", small_private, small_public)],
        [{"kid": "base-current", "status": "retired", "public_pem": current_public}],
    ]
    for config in cases:
        with pytest.raises(BaseKeyConfigError) as caught:
            keyset_from_config(config)
        _assert_safe_error(caught.value, current_private)
        _assert_safe_error(caught.value, other_private)
        _assert_safe_error(caught.value, small_private)


def test_claim_boundaries(keys):
    private_pem, public_pem = keys[0]
    keyset = _active(keys)
    issued = int(time.time())
    for audience in ("edu-api:ent", "edu-api:pf", "edu-api:cs", "edu-api:stu", "edu-api:rpt"):
        for user_type in ("employee", "admin", "student"):
            token = issue_access_token(
                keyset,
                sub="42",
                sid=SID,
                audience=audience,
                user_type=user_type,
                ttl_seconds=60,
            )
            claims = verify_token(keyset, token, audience=audience, token_use=ACCESS_TOKEN_USE)
            assert claims["aud"] == audience
            assert claims["user_type"] == user_type
    for audience in ("ent-api", "edu-auth:token-exchange", "https://example.invalid"):
        with pytest.raises(BaseTokenError):
            issue_access_token(
                keyset, sub="42", sid=SID, audience=audience, user_type="employee"
            )
        with pytest.raises(BaseTokenError):
            issue_service_token(keyset, sub="svc:report-bot", sid=SID, audience=audience)
        with pytest.raises(BaseTokenError):
            verify_token(keyset, _issue(keys), audience=audience, token_use=ACCESS_TOKEN_USE)
    for user_type in ("teacher", "guest", "service"):
        with pytest.raises(BaseTokenError):
            issue_access_token(
                keyset, sub="42", sid=SID, audience="edu-api:ent", user_type=user_type
            )
    for sub in ("0", "01", "42 ", "svc:report-bot", ""):
        with pytest.raises(BaseTokenError):
            issue_access_token(
                keyset, sub=sub, sid=SID, audience="edu-api:ent", user_type="employee"
            )
    for sub in ("42", "svc:", "svc:bad id", ""):
        with pytest.raises(BaseTokenError):
            issue_service_token(keyset, sub=sub, sid=SID, audience="edu-api:rpt")
    for sid in ("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee".upper(), "11111111-1111-4111-8111-11111111111", "not-a-uuid"):
        with pytest.raises(BaseTokenError):
            issue_access_token(
                keyset, sub="42", sid=sid, audience="edu-api:ent", user_type="employee"
            )
    with pytest.raises(BaseTokenError):
        issue_access_token(
            keyset, sub="42", sid=SID, audience="edu-api:ent", user_type="employee", ttl_seconds=3601
        )
    base = {
        "iss": ISSUER,
        "aud": "edu-api:ent",
        "sub": "42",
        "sid": SID,
        "user_type": "employee",
        "token_use": ACCESS_TOKEN_USE,
        "iat": issued,
        "nbf": issued,
    }
    for payload in (
        {**base, "exp": issued},
        {**base, "exp": issued - 1},
        {**base, "exp": issued + 3601},
        {**base, "aud": ["edu-api:ent", "edu-api:pf"], "exp": issued + 60},
        {**base, "token_use": SERVICE_TOKEN_USE, "exp": issued + 60},
    ):
        forged = jwt.encode(
            payload, private_pem, algorithm="RS256", headers={"kid": "base-current", "typ": "JWT"}
        )
        with pytest.raises(BaseTokenError):
            verify_token(keyset, forged, audience="edu-api:ent", token_use=ACCESS_TOKEN_USE)
    service = issue_service_token(keyset, sub="svc:report-bot", sid=SID, audience="edu-api:cs")
    service_claims = jwt.decode(service, public_pem, algorithms=["RS256"], audience="edu-api:cs")
    service_claims["user_type"] = "employee"
    tainted = jwt.encode(
        service_claims, private_pem, algorithm="RS256", headers={"kid": "base-current", "typ": "JWT"}
    )
    with pytest.raises(BaseTokenError):
        verify_token(keyset, tainted, audience="edu-api:cs", token_use=SERVICE_TOKEN_USE)
    from app.modules.auth.schemas import Login
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Login.model_validate({"username": "employee", "password": "secret", "audience": "edu-api:stu"})


def test_key_loading_priority_and_failures(keys, monkeypatch, tmp_path):
    current_private, current_public = keys[0]
    other_private, other_public = keys[1]
    file_config = [_entry("from-file", "active", current_private, current_public)]
    env_config = [_entry("from-env", "active", other_private, other_public)]
    key_file = tmp_path / "base-keys.json"
    key_file.write_text(json.dumps(file_config), encoding="utf-8")
    monkeypatch.setenv("BASE_JWT_KEYS_FILE", str(key_file))
    monkeypatch.setenv("BASE_JWT_KEYS", json.dumps(env_config))
    loaded = load_keyset()
    assert [key.kid for key in loaded.keys] == ["from-file"]
    monkeypatch.setenv("BASE_JWT_KEYS_FILE", "   ")
    assert [key.kid for key in load_keyset().keys] == ["from-env"]
    monkeypatch.setenv("BASE_JWT_KEYS_FILE", str(tmp_path / "missing-keys.json"))
    with pytest.raises(BaseKeyConfigError) as missing:
        load_keyset()
    _assert_safe_error(missing.value, current_private)
    broken = tmp_path / "broken.json"
    broken.write_text("{not-json " + current_private, encoding="utf-8")
    monkeypatch.setenv("BASE_JWT_KEYS_FILE", str(broken))
    with pytest.raises(BaseKeyConfigError) as invalid:
        load_keyset()
    _assert_safe_error(invalid.value, current_private)
    monkeypatch.delenv("BASE_JWT_KEYS_FILE")
    monkeypatch.setenv("BASE_JWT_KEYS", "{")
    with pytest.raises(BaseKeyConfigError) as env_invalid:
        load_keyset()
    _assert_safe_error(env_invalid.value, current_private)
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "app" / "core" / "security" / "base_jwt.py"
    ).read_text(encoding="utf-8")
    router = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "app" / "core" / "security" / "jwks_router.py"
    ).read_text(encoding="utf-8")
    assert "print(" not in source and "print(" not in router
    assert "logger" not in source and "logger" not in router
