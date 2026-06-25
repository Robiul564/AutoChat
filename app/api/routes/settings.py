from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.core.config import settings as app_settings
from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access
from app.services import ai

router = APIRouter(prefix="/api/businesses/{business_id}/settings/ai", tags=["settings"])


@router.get("", response_model=schemas.AISettingsOut)
def read_ai_settings(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return ai_settings_out(ai.get_settings(db, business_id))


@router.patch("", response_model=schemas.AISettingsOut)
def update_ai_settings(business_id: int, payload: schemas.AISettingsUpdate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    settings = ai.get_settings(db, business_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return ai_settings_out(settings)


def ai_settings_out(settings) -> dict:
    return {
        "id": settings.id,
        "business_id": settings.business_id,
        "system_prompt": settings.system_prompt,
        "tone": settings.tone,
        "fallback_message": settings.fallback_message,
        "workflow_config_json": settings.workflow_config_json,
        "openai_configured": bool(app_settings.openai_api_key),
    }
