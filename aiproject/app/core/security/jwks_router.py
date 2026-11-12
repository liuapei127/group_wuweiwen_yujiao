"""Public JWKS for BASE RS256. Private keys stay outside this response."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.security.base_jwt import BaseKeyConfigError, jwks_document, load_keyset

router = APIRouter(tags=["base-jwks"])


@router.get("/api/v1/auth/jwks")
def publish_jwks():
    try:
        document = jwks_document(load_keyset())
    except BaseKeyConfigError:
        return JSONResponse(
            status_code=503,
            content={"detail": "BASE 公钥未就绪"},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        document,
        headers={"Cache-Control": "public, max-age=60"},
    )
