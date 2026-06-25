from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


def overview(db: Session, business_id: int, start: datetime | None = None, end: datetime | None = None) -> dict:
    query = db.query(models.Message).filter(models.Message.business_id == business_id)
    if start:
        query = query.filter(models.Message.created_at >= start)
    if end:
        query = query.filter(models.Message.created_at <= end)
    total = query.count()
    ai = query.filter(models.Message.ai_generated.is_(True)).count()
    inbound = query.filter(models.Message.direction == "inbound").count()
    handoffs = db.query(models.Conversation).filter(models.Conversation.business_id == business_id, models.Conversation.status == "pending_handoff").count()
    return {
        "message_count": total,
        "inbound_count": inbound,
        "ai_message_count": ai,
        "automation_rate": round(ai / total, 4) if total else 0,
        "handoff_count": handoffs,
        "handoff_rate": round(handoffs / inbound, 4) if inbound else 0,
    }


def conversation_trends(db: Session, business_id: int) -> list[dict]:
    rows = (
        db.query(func.date(models.Message.created_at), func.count(models.Message.id))
        .filter(models.Message.business_id == business_id)
        .group_by(func.date(models.Message.created_at))
        .all()
    )
    return [{"date": str(day), "messages": count} for day, count in rows]

