import base64
import hashlib
import hmac
import json
from typing import Any

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app import models


def derive_slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return "-".join(part for part in cleaned.split("-") if part) or "business"


def wrap_secret(value: str) -> str:
    digest = hmac.new(settings.app_secret.encode(), value.encode(), hashlib.sha256).digest()
    payload = {"v": value, "mac": base64.urlsafe_b64encode(digest).decode()}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def unwrap_secret(encrypted_value: str) -> str:
    payload = json.loads(base64.urlsafe_b64decode(encrypted_value.encode()).decode())
    value = payload["v"]
    expected = hmac.new(settings.app_secret.encode(), value.encode(), hashlib.sha256).digest()
    actual = base64.urlsafe_b64decode(payload["mac"].encode())
    if not hmac.compare_digest(expected, actual):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Secret integrity check failed")
    return value


async def verify_meta_signature(request: Request, x_hub_signature_256: str | None = Header(default=None)) -> None:
    if not settings.meta_app_secret:
        return
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Meta signature")
    body = await request.body()
    expected = hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(f"sha256={expected}", x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Meta signature")


def get_actor_email(
    x_user_email: str | None = Header(default="owner@example.com"),
    x_admin_key: str | None = Header(default=None),
) -> str:
    if settings.auth_mode == "admin_key":
        if not settings.admin_api_key or not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API key")
    return x_user_email or "owner@example.com"


def require_platform_admin(actor_email: str) -> None:
    if actor_email.lower() not in settings.platform_admin_email_set:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is managed by the service owner")


def require_business_access(db: Session, business_id: int, actor_email: str) -> models.Business:
    business = db.get(models.Business, business_id)
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    user = db.query(models.User).filter(models.User.email == actor_email).one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a business member")
    membership = (
        db.query(models.BusinessUser)
        .filter(
            models.BusinessUser.business_id == business_id,
            models.BusinessUser.user_id == user.id,
            models.BusinessUser.status == "active",
        )
        .one_or_none()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a business member")
    return business


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("***" if "secret" in key or "token" in key else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
