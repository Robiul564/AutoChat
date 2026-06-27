import base64
from datetime import datetime
import hashlib
import hmac
import logging
import re
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

logger = logging.getLogger(__name__)


def webhook_verify_token_for_business(business_id: int) -> str:
    digest = hmac.new(settings.app_secret.encode(), f"whatsapp-webhook:{business_id}".encode(), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return f"biz_{business_id}_{token}"


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


def resolve_business_webhook_account(db: Session, business_id: int) -> models.WhatsAppAccount | None:
    return (
        db.query(models.WhatsAppAccount)
        .filter(
            models.WhatsAppAccount.business_id == business_id,
            models.WhatsAppAccount.status.in_(["connected", "reauth_required"]),
        )
        .order_by(models.WhatsAppAccount.created_at.desc())
        .first()
    )


def send_text(db: Session, business_id: int, conversation_id: int, customer_id: int, body: str, ai_generated: bool = False) -> models.Message:
    account = resolve_reply_account(db, business_id, conversation_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No connected WhatsApp account for business")
    provider_id = f"mock-{account.phone_number_id}-{uuid4().hex[:12]}"
    provider_status = "mock_saved"
    message_status = "mock_saved"
    provider_payload = {"mock": True, "phone_number_id": account.phone_number_id}

    if should_send_live(db, account):
        provider_id = f"pending-{account.phone_number_id}-{uuid4().hex[:12]}"
        provider_status = "pending_provider"
        message_status = "pending_provider"
        logger.info(
            "Attempting WhatsApp live send: business=%s conversation=%s customer=%s phone_number_id=%s",
            business_id,
            conversation_id,
            customer_id,
            account.phone_number_id,
        )
        try:
            provider_payload = send_text_live(db, account, customer_id, body)
            provider_id = provider_payload.get("messages", [{}])[0].get("id", provider_id)
            provider_status = "sent_to_provider"
            message_status = "accepted_by_meta"
        except HTTPException as exc:
            fallback_sent = False
            if _should_try_utility_template(exc) and settings.whatsapp_utility_template_name:
                try:
                    template_payload = send_utility_template_live(db, account, customer_id, body)
                    provider_payload = {
                        "fallback_used": "utility_template",
                        "text_send_error": exc.detail,
                        "template_send": template_payload,
                    }
                    provider_id = template_payload.get("messages", [{}])[0].get("id", provider_id)
                    provider_status = "sent_to_provider"
                    message_status = "accepted_by_meta"
                    fallback_sent = True
                    logger.info(
                        "Utility template fallback sent for business=%s phone_number_id=%s template=%s",
                        business_id,
                        account.phone_number_id,
                        settings.whatsapp_utility_template_name,
                    )
                except HTTPException as template_exc:
                    provider_payload = {
                        "error": template_exc.detail,
                        "text_send_error": exc.detail,
                        "phone_number_id": account.phone_number_id,
                    }
            if not fallback_sent:
                provider_payload = provider_payload if provider_payload.get("error") else {"error": exc.detail, "phone_number_id": account.phone_number_id}
                provider_status = "failed"
                message_status = "failed"
                logger.warning("WhatsApp live send failed for business=%s phone_number_id=%s error=%s", business_id, account.phone_number_id, exc.detail)
    else:
        logger.info(
            "WhatsApp reply saved without live send: mode=%s business=%s phone_number_id=%s",
            settings.whatsapp_send_mode,
            business_id,
            account.phone_number_id,
        )

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


def should_send_live(db: Session, account: models.WhatsAppAccount) -> bool:
    mode = settings.whatsapp_send_mode.lower()
    if mode in {"off", "disabled"}:
        return False
    if mode == "mock" and not settings.is_production:
        return False
    if mode in {"live", "auto", "mock"}:
        return bool(account.phone_number_id and db.get(models.Secret, account.access_token_secret_id))
    return False


def resolve_reply_account(db: Session, business_id: int, conversation_id: int) -> models.WhatsAppAccount | None:
    inbound = (
        db.query(models.Message)
        .filter(
            models.Message.business_id == business_id,
            models.Message.conversation_id == conversation_id,
            models.Message.direction == "inbound",
        )
        .order_by(models.Message.created_at.desc())
        .first()
    )
    phone_number_id = None
    if inbound:
        metadata = (inbound.provider_payload_json or {}).get("_metadata", {})
        phone_number_id = metadata.get("phone_number_id")
    query = db.query(models.WhatsAppAccount).filter(
        models.WhatsAppAccount.business_id == business_id,
        models.WhatsAppAccount.status == "connected",
    )
    if phone_number_id:
        account = query.filter(models.WhatsAppAccount.phone_number_id == str(phone_number_id)).one_or_none()
        if account:
            return account
    return query.order_by(models.WhatsAppAccount.created_at.desc()).first()


def send_text_live(db: Session, account: models.WhatsAppAccount, customer_id: int, body: str) -> dict[str, Any]:
    customer, token, url = _resolve_customer_token_url(db, account, customer_id)
    recipient = _normalize_whatsapp_recipient(customer.phone_e164 or customer.whatsapp_user_id)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    return _post_messages(url, token, payload, account.phone_number_id, recipient)


def send_utility_template_live(db: Session, account: models.WhatsAppAccount, customer_id: int, body_text: str) -> dict[str, Any]:
    customer, token, url = _resolve_customer_token_url(db, account, customer_id)
    recipient = _normalize_whatsapp_recipient(customer.phone_e164 or customer.whatsapp_user_id)
    template_name = settings.whatsapp_utility_template_name.strip()
    language = settings.whatsapp_utility_template_lang.strip() or "en_US"
    if not template_name:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WHATSAPP_UTILITY_TEMPLATE_NAME is not configured")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": body_text}],
                }
            ],
        },
    }
    return _post_messages(url, token, payload, account.phone_number_id, recipient)


def _resolve_customer_token_url(db: Session, account: models.WhatsAppAccount, customer_id: int) -> tuple[models.Customer, str, str]:
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    secret = db.get(models.Secret, account.access_token_secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp access token secret is missing")
    token = unwrap_secret(secret.encrypted_value)
    url = f"{settings.whatsapp_graph_api_url.rstrip('/')}/{account.phone_number_id}/messages"
    return customer, token, url


def _normalize_whatsapp_recipient(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return value
    compact = re.sub(r"[\s().-]", "", value)
    if compact.startswith("+"):
        normalized = compact
    elif compact.isdigit():
        normalized = f"+{compact}"
    else:
        normalized = value
    if normalized != value:
        logger.info("Normalized WhatsApp recipient from %s to %s", value, normalized)
    return normalized

def _post_messages(url: str, token: str, payload: dict[str, Any], phone_number_id: str, to: str) -> dict[str, Any]:
    logger.info("Posting WhatsApp message to Meta: phone_number_id=%s to=%s type=%s", phone_number_id, to, payload.get("type"))
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info("WhatsApp live send accepted by Meta for phone_number_id=%s customer=%s", phone_number_id, to)
            return data
    except httpx.HTTPStatusError as exc:
        meta_error = _safe_meta_error(exc.response)
        logger.warning(
            "WhatsApp Meta HTTP error: phone_number_id=%s to=%s status=%s meta_error=%s",
            phone_number_id,
            to,
            exc.response.status_code,
            meta_error,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "WhatsApp send failed",
                "http_status": exc.response.status_code,
                "meta_error": meta_error,
            },
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp transport error: phone_number_id=%s to=%s error=%s", phone_number_id, to, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": f"WhatsApp send failed: {exc}"}) from exc


def _safe_meta_error(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {"raw": response.text}
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return error
    return {"raw": data}


def _should_try_utility_template(exc: HTTPException) -> bool:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    meta_error = detail.get("meta_error") if isinstance(detail.get("meta_error"), dict) else {}
    code = meta_error.get("code")
    message = str(meta_error.get("message", "")).lower()
    should_fallback = code == 131047 or "outside the 24-hour" in message or "outside the customer service window" in message
    if should_fallback:
        logger.info("Utility template fallback eligible: code=%s message=%s", code, message)
    return should_fallback





