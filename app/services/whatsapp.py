from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings
from app.core.security import unwrap_secret
from app.services.audit import audit
from app.services.secrets import rotate_secret, store_secret


def save_account(db: Session, business_id: int, payload: schemas.WhatsAppAccountCreate) -> models.WhatsAppAccount:
    app_secret = store_secret(db, business_id, "whatsapp_app_secret", payload.app_secret)
    token = store_secret(db, business_id, "whatsapp_access_token", payload.access_token, payload.token_expires_at)
    verify = store_secret(db, business_id, "whatsapp_verify_token", payload.webhook_verify_token) if payload.webhook_verify_token else None
    account = models.WhatsAppAccount(
        business_id=business_id,
        app_id=payload.app_id,
        app_secret_secret_id=app_secret.id,
        access_token_secret_id=token.id,
        phone_number_id=payload.phone_number_id,
        waba_id=payload.waba_id,
        display_phone_number=payload.display_phone_number,
        webhook_verify_token_secret_id=verify.id if verify else None,
        token_expires_at=payload.token_expires_at,
        status="connected" if payload.access_token and payload.phone_number_id else "pending_validation",
        last_validated_at=datetime.utcnow() if payload.access_token and payload.phone_number_id else None,
    )
    db.add(account)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number ID is already connected") from exc
    audit(db, business_id=business_id, action="whatsapp.account.saved", entity_type="whatsapp_account", entity_id=str(account.id), after=payload.model_dump())
    db.commit()
    db.refresh(account)
    return account


def validate_account(db: Session, account: models.WhatsAppAccount) -> dict[str, Any]:
    account.status = "connected" if account.phone_number_id else "invalid"
    account.last_validated_at = datetime.utcnow()
    audit(db, business_id=account.business_id, action="whatsapp.account.validated", entity_type="whatsapp_account", entity_id=str(account.id), after={"status": account.status})
    db.commit()
    db.refresh(account)
    return {"valid": account.status == "connected", "status": account.status, "checked_at": account.last_validated_at}


def rotate_token(db: Session, account: models.WhatsAppAccount, payload: schemas.TokenRotate) -> models.WhatsAppAccount:
    rotate_secret(db, account.access_token_secret_id, payload.access_token, payload.expires_at)
    account.token_expires_at = payload.expires_at
    account.status = "connected"
    account.last_validated_at = datetime.utcnow()
    audit(db, business_id=account.business_id, action="whatsapp.token.rotated", entity_type="whatsapp_account", entity_id=str(account.id))
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, account: models.WhatsAppAccount) -> None:
    account_id = account.id
    business_id = account.business_id
    phone_number_id = account.phone_number_id
    display_phone_number = account.display_phone_number
    db.delete(account)
    audit(
        db,
        business_id=business_id,
        action="whatsapp.account.deleted",
        entity_type="whatsapp_account",
        entity_id=str(account_id),
        before={"phone_number_id": phone_number_id, "display_phone_number": display_phone_number},
    )
    db.commit()


def resolve_tenant(db: Session, metadata: dict[str, Any], waba_id: str | None = None) -> models.WhatsAppAccount | None:
    phone_number_id = metadata.get("phone_number_id")
    query = db.query(models.WhatsAppAccount).filter(models.WhatsAppAccount.status.in_(["connected", "reauth_required"]))
    if phone_number_id:
        account = query.filter(models.WhatsAppAccount.phone_number_id == str(phone_number_id)).one_or_none()
        if account:
            return account
    if waba_id:
        return query.filter(models.WhatsAppAccount.waba_id == str(waba_id)).first()
    return None


def send_text(db: Session, business_id: int, conversation_id: int, customer_id: int, body: str, ai_generated: bool = False) -> models.Message:
    account = db.query(models.WhatsAppAccount).filter(models.WhatsAppAccount.business_id == business_id, models.WhatsAppAccount.status == "connected").first()
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No connected WhatsApp account for business")
    provider_id = f"mock-{account.phone_number_id}-{uuid4().hex[:12]}"
    provider_status = "sent_to_provider"
    message_status = "sent_to_provider"
    provider_payload = {"mock": True, "phone_number_id": account.phone_number_id}

    if settings.whatsapp_send_mode.lower() == "live":
        provider_id = f"pending-{account.phone_number_id}-{uuid4().hex[:12]}"
        provider_status = "pending_provider"
        message_status = "pending_provider"
        try:
            provider_payload = send_text_live(db, account, customer_id, body)
            provider_id = provider_payload.get("messages", [{}])[0].get("id", provider_id)
            provider_status = "sent_to_provider"
            message_status = "sent_to_provider"
        except HTTPException as exc:
            provider_payload = {"error": exc.detail, "phone_number_id": account.phone_number_id}
            provider_status = "failed"
            message_status = "failed"

    message = models.Message(
        business_id=business_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        direction="outbound",
        type="text",
        body=body,
        ai_generated=ai_generated,
        provider_message_id=provider_id,
        provider_status=provider_status,
        status=message_status,
        sent_at=datetime.utcnow(),
        provider_payload_json=provider_payload,
    )
    db.add(message)
    conversation = db.get(models.Conversation, conversation_id)
    if conversation and conversation.business_id == business_id:
        conversation.last_message_at = message.sent_at
    audit(db, business_id=business_id, action="message.outbound.sent", entity_type="message", entity_id=provider_id, actor_type="system")
    db.commit()
    db.refresh(message)
    return message


def send_text_live(db: Session, account: models.WhatsAppAccount, customer_id: int, body: str) -> dict[str, Any]:
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    secret = db.get(models.Secret, account.access_token_secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp access token secret is missing")
    token = unwrap_secret(secret.encrypted_value)
    url = f"{settings.whatsapp_graph_api_url.rstrip('/')}/{account.phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": customer.whatsapp_user_id,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"WhatsApp send failed: {exc}") from exc
