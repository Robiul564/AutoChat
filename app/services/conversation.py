from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import models


def get_or_create_customer(db: Session, business_id: int, whatsapp_user_id: str, phone: str | None = None, name: str | None = None) -> models.Customer:
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.business_id == business_id, models.Customer.whatsapp_user_id == whatsapp_user_id)
        .one_or_none()
    )
    if customer:
        customer.last_seen_at = datetime.utcnow()
        if name and not customer.name:
            customer.name = name
        return customer
    customer = models.Customer(
        business_id=business_id,
        whatsapp_user_id=whatsapp_user_id,
        phone_e164=phone,
        name=name,
    )
    db.add(customer)
    db.flush()
    return customer


def get_or_create_conversation(db: Session, business_id: int, customer_id: int) -> models.Conversation:
    conversation = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.business_id == business_id,
            models.Conversation.customer_id == customer_id,
            models.Conversation.channel == "whatsapp",
            models.Conversation.status.in_(["open", "pending_handoff"]),
        )
        .order_by(models.Conversation.created_at.desc())
        .first()
    )
    if conversation:
        return conversation
    conversation = models.Conversation(business_id=business_id, customer_id=customer_id, status="open", ai_enabled=True)
    db.add(conversation)
    db.flush()
    return conversation


def add_inbound_message(db: Session, business_id: int, payload: dict[str, Any]) -> models.Message:
    provider_message_id = payload.get("provider_message_id")
    sender = payload.get("from")
    if not provider_message_id or not sender:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inbound WhatsApp message is missing provider id or sender")
    existing = db.query(models.Message).filter(models.Message.business_id == business_id, models.Message.provider_message_id == provider_message_id).one_or_none()
    if existing:
        return existing
    customer = get_or_create_customer(db, business_id, sender, sender, payload.get("profile_name"))
    conversation = get_or_create_conversation(db, business_id, customer.id)
    created_at = datetime.utcnow()
    message = models.Message(
        business_id=business_id,
        conversation_id=conversation.id,
        customer_id=customer.id,
        direction="inbound",
        type=payload.get("type", "text"),
        body=payload.get("body", ""),
        provider_message_id=provider_message_id,
        provider_status="received",
        provider_payload_json=payload.get("raw", {}),
        status="received",
        created_at=created_at,
    )
    db.add(message)
    conversation.last_message_at = created_at
    db.commit()
    db.refresh(message)
    return message


def require_conversation(db: Session, business_id: int, conversation_id: int) -> models.Conversation:
    conversation = (
        db.query(models.Conversation)
        .filter(models.Conversation.business_id == business_id, models.Conversation.id == conversation_id)
        .one_or_none()
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


def update_status_from_provider(db: Session, business_id: int, payload: dict[str, Any]) -> None:
    provider_id = payload.get("id")
    status_value = payload.get("status")
    if not provider_id or not status_value:
        return
    message = db.query(models.Message).filter(models.Message.business_id == business_id, models.Message.provider_message_id == provider_id).one_or_none()
    try:
        occurred = datetime.utcfromtimestamp(int(payload.get("timestamp", "0"))) if payload.get("timestamp") else datetime.utcnow()
    except (TypeError, ValueError):
        occurred = datetime.utcnow()
    existing = (
        db.query(models.MessageStatusEvent)
        .filter(
            models.MessageStatusEvent.provider_message_id == provider_id,
            models.MessageStatusEvent.status == status_value,
            models.MessageStatusEvent.occurred_at == occurred,
        )
        .one_or_none()
    )
    if existing:
        return
    db.add(
        models.MessageStatusEvent(
            business_id=business_id,
            message_id=message.id if message else None,
            provider_message_id=provider_id,
            status=status_value,
            payload_json=payload,
            occurred_at=occurred,
        )
    )
    if message:
        message.provider_status = status_value
        message.status = status_value
        message.provider_payload_json = payload
        if payload.get("errors"):
            message.error_code = str(payload["errors"][0].get("code", "")) if isinstance(payload["errors"], list) and payload["errors"] else None
        if status_value == "delivered":
            message.delivered_at = occurred
        if status_value == "read":
            message.read_at = occurred
    db.commit()
