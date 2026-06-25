from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access
from app.services.onboarding import QUESTIONS

router = APIRouter(prefix="/api/businesses/{business_id}/onboarding", tags=["onboarding"])


@router.get("/latest", response_model=schemas.OnboardingSessionOut | None)
def latest_session(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return (
        db.query(models.OnboardingSession)
        .filter(models.OnboardingSession.business_id == business_id)
        .order_by(models.OnboardingSession.started_at.desc())
        .first()
    )


@router.get("/questions")
def onboarding_questions(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return QUESTIONS
