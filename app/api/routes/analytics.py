from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access
from app.services import analytics

router = APIRouter(prefix="/api/businesses/{business_id}/analytics", tags=["analytics"])


@router.get("/overview")
def overview(business_id: int, start: datetime | None = None, end: datetime | None = None, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return analytics.overview(db, business_id, start, end)


@router.get("/conversations")
def conversations(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return analytics.conversation_trends(db, business_id)


@router.get("/ai-costs")
def ai_costs(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return {"provider": "mock", "tokens": 0, "cost": 0, "currency": "USD"}
