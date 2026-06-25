from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access
from app.services import conversation, whatsapp

router = APIRouter(prefix="/api/businesses/{business_id}", tags=["conversations"])


@router.get("/conversations", response_model=list[schemas.ConversationOut])
def list_conversations(business_id: int, status_filter: str | None = None, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    query = db.query(models.Conversation).filter(models.Conversation.business_id == business_id)
    if status_filter:
        query = query.filter(models.Conversation.status == status_filter)
    conversations = query.order_by(models.Conversation.last_message_at.desc().nullslast(), models.Conversation.created_at.desc()).all()
    return [conversation_out(db, item) for item in conversations]


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationDetail)
def get_conversation(business_id: int, conversation_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    conv = conversation.require_conversation(db, business_id, conversation_id)
    messages = db.query(models.Message).filter(models.Message.business_id == business_id, models.Message.conversation_id == conversation_id).order_by(models.Message.created_at).all()
    return {"conversation": conversation_out(db, conv), "messages": messages}


@router.post("/conversations/{conversation_id}/messages", response_model=schemas.MessageOut)
def send_agent_reply(business_id: int, conversation_id: int, payload: schemas.MessageCreate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    conv = conversation.require_conversation(db, business_id, conversation_id)
    return whatsapp.send_text(db, business_id, conversation_id, conv.customer_id, payload.body, ai_generated=False)


@router.post("/conversations/{conversation_id}/handoff", response_model=schemas.ConversationOut)
def handoff(business_id: int, conversation_id: int, payload: schemas.HandoffRequest, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    conv = conversation.require_conversation(db, business_id, conversation_id)
    if payload.assigned_user_id:
        membership = (
            db.query(models.BusinessUser)
            .filter(models.BusinessUser.business_id == business_id, models.BusinessUser.user_id == payload.assigned_user_id, models.BusinessUser.status == "active")
            .one_or_none()
        )
        if not membership:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignee is not a business member")
    conv.status = "pending_handoff"
    conv.assigned_user_id = payload.assigned_user_id
    conv.ai_enabled = False
    db.commit()
    db.refresh(conv)
    return conv


@router.patch("/customers/{customer_id}")
def update_customer(business_id: int, customer_id: int, payload: dict, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    customer = db.query(models.Customer).filter(models.Customer.business_id == business_id, models.Customer.id == customer_id).one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    for key in ("name", "profile_json", "tags_json"):
        if key in payload:
            setattr(customer, key, payload[key])
    db.commit()
    db.refresh(customer)
    return customer


def conversation_out(db: Session, conv: models.Conversation) -> dict:
    customer = db.get(models.Customer, conv.customer_id)
    last_message = (
        db.query(models.Message)
        .filter(models.Message.business_id == conv.business_id, models.Message.conversation_id == conv.id)
        .order_by(models.Message.created_at.desc())
        .first()
    )
    return {
        "id": conv.id,
        "business_id": conv.business_id,
        "customer_id": conv.customer_id,
        "channel": conv.channel,
        "status": conv.status,
        "ai_enabled": conv.ai_enabled,
        "language": conv.language,
        "last_message_at": conv.last_message_at,
        "summary": conv.summary,
        "created_at": conv.created_at,
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.phone_e164 if customer else None,
        "last_message_body": last_message.body if last_message else None,
    }
