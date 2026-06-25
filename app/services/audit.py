from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.core.security import redact


def audit(
    db: Session,
    *,
    business_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor_user_id: int | None = None,
    actor_type: str = "user",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> models.AuditLog:
    log = models.AuditLog(
        business_id=business_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=redact(before) if before else None,
        after_json=redact(after) if after else None,
    )
    db.add(log)
    return log
