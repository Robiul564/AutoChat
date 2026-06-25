from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.core.security import unwrap_secret, wrap_secret


def store_secret(db: Session, business_id: int | None, name: str, value: str, expires_at: datetime | None = None) -> models.Secret:
    secret = models.Secret(
        business_id=business_id,
        name=name,
        encrypted_value=wrap_secret(value),
        expires_at=expires_at,
    )
    db.add(secret)
    db.flush()
    return secret


def rotate_secret(db: Session, secret_id: int, value: str, expires_at: datetime | None = None) -> models.Secret:
    secret = db.get(models.Secret, secret_id)
    if not secret:
        raise ValueError("Secret not found")
    secret.encrypted_value = wrap_secret(value)
    secret.version += 1
    secret.rotated_at = datetime.utcnow()
    secret.expires_at = expires_at
    db.flush()
    return secret


def reveal_secret(db: Session, secret_id: int) -> str:
    secret = db.get(models.Secret, secret_id)
    if not secret:
        raise ValueError("Secret not found")
    return unwrap_secret(secret.encrypted_value)
