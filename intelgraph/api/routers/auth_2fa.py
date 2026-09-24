from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from intelgraph.api.auth import (
    get_totp_manager,
    login_with_2fa_step1,
    validate_token,  # noqa: F401
    verify_2fa_code,
)
from intelgraph.api.models import Auth2FAEnable, Auth2FALogin, Auth2FAVerify

router = APIRouter(prefix="/auth/2fa", tags=["auth"])


def _require_user(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[7:]
    from intelgraph.api.auth import validate_token as vt

    uid = vt(token)
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return uid


@router.post("/enable")
def enable_2fa(request: Request, body: Auth2FAEnable):
    user_id = _require_user(request)
    totp_manager = get_totp_manager()
    result = totp_manager.enable(user_id, issuer=body.issuer or "IntelGraph")
    return result


@router.post("/verify")
def verify_2fa(body: Auth2FAVerify):
    result = verify_2fa_code(body.temp_token, body.code)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA code")
    return result


@router.post("/verify-setup")
def verify_setup_2fa(request: Request, body: dict):
    """Verify TOTP code after enabling 2FA (setup verification)."""
    user_id = _require_user(request)
    code = body.get("code", "")
    if not code or len(code) != 6:
        raise HTTPException(status_code=400, detail="6-digit code required")
    totp_manager = get_totp_manager()
    if totp_manager.verify(user_id, code):
        return {"valid": True, "message": "2FA verified successfully"}
    return {"valid": False, "message": "Invalid code"}


@router.post("/disable")
def disable_2fa(request: Request):
    user_id = _require_user(request)
    totp_manager = get_totp_manager()
    if not totp_manager.disable(user_id):
        raise HTTPException(status_code=404, detail="2FA not enabled")
    return {"status": "disabled"}


@router.get("/status")
def status_2fa(request: Request):
    user_id = _require_user(request)
    totp_manager = get_totp_manager()
    return totp_manager.get_status(user_id)


@router.post("/login")
def login_2fa(body: Auth2FALogin):
    result = login_with_2fa_step1(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result
