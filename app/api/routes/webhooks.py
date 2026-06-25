import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings
from app.core.db import get_db
from app.core.security import unwrap_secret, verify_meta_signature
from app.services import whatsapp
from app.workers.queue import Event, event_queue

router = APIRouter(prefix="/webhooks/meta/whatsapp", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.get("")
@router.get("/")
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    mode = (hub_mode or "").strip()
    verify_token = (hub_verify_token or "").strip()
    challenge = (hub_challenge or "").strip()
    if mode == "subscribe" and challenge and verify_token_matches(db, verify_token):
        return Response(content=challenge, media_type="text/plain")
    logger.warning(
        "Meta webhook challenge rejected: mode=%r has_token=%s has_challenge=%s token_length=%s",
        mode,
        bool(verify_token),
        bool(challenge),
        len(verify_token),
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook challenge rejected")


@router.get("/business/{business_id}")
@router.get("/business/{business_id}/")
def verify_business_webhook(
    business_id: int,
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    mode = (hub_mode or "").strip()
    verify_token = (hub_verify_token or "").strip()
    challenge = (hub_challenge or "").strip()
    if mode == "subscribe" and challenge and verify_token_matches(db, verify_token, business_id=business_id):
        return Response(content=challenge, media_type="text/plain")
    logger.warning(
        "Meta business webhook challenge rejected: business_id=%s mode=%r has_token=%s has_challenge=%s token_length=%s",
        business_id,
        mode,
        bool(verify_token),
        bool(challenge),
        len(verify_token),
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook challenge rejected")


@router.post("", response_model=schemas.WebhookAccepted)
@router.post("/", response_model=schemas.WebhookAccepted)
async def receive_webhook(request: Request, db: Session = Depends(get_db), _: None = Depends(verify_meta_signature)):
    payload = await request.json()
    accepted = 0
    for item in extract_events(payload, db):
        await event_queue.publish(item)
        accepted += 1
    logger.info("Meta webhook accepted %s event(s) on platform endpoint", accepted)
    return {"accepted": True, "events": accepted}


@router.post("/business/{business_id}", response_model=schemas.WebhookAccepted)
@router.post("/business/{business_id}/", response_model=schemas.WebhookAccepted)
async def receive_business_webhook(business_id: int, request: Request, db: Session = Depends(get_db), _: None = Depends(verify_meta_signature)):
    payload = await request.json()
    accepted = 0
    for item in extract_events(payload, db, business_id=business_id):
        await event_queue.publish(item)
        accepted += 1
    logger.info("Meta webhook accepted %s event(s) on business endpoint %s", accepted, business_id)
    return {"accepted": True, "events": accepted}


def verify_token_matches(db: Session, verify_token: str, business_id: int | None = None) -> bool:
    if not verify_token:
        return False
    if business_id is not None and hmac.compare_digest(verify_token, whatsapp.webhook_verify_token_for_business(business_id)):
        return True
    expected = settings.webhook_verify_token.strip()
    if expected and hmac.compare_digest(verify_token, expected):
        return True
    query = (
        db.query(models.Secret)
        .join(models.WhatsAppAccount, models.WhatsAppAccount.webhook_verify_token_secret_id == models.Secret.id)
        .filter(models.Secret.name == "whatsapp_verify_token")
    )
    if business_id is not None:
        query = query.filter(models.WhatsAppAccount.business_id == business_id)
    secrets = query.all()
    for secret in secrets:
        try:
            account_token = unwrap_secret(secret.encrypted_value).strip()
        except Exception:
            logger.exception("Could not unwrap WhatsApp webhook verify token secret %s", secret.id)
            continue
        if account_token and hmac.compare_digest(verify_token, account_token):
            return True
    return False


def extract_events(payload: dict[str, Any], db: Session, business_id: int | None = None) -> list[Event]:
    events: list[Event] = []
    for entry in payload.get("entry", []):
        waba_id = str(entry.get("id")) if entry.get("id") else None
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            account = whatsapp.resolve_tenant(db, metadata, waba_id=waba_id)
            if not account and business_id is not None:
                account = whatsapp.resolve_business_webhook_account(db, business_id)
            if not account:
                logger.warning(
                    "Ignoring Meta webhook event because no WhatsApp account matched metadata phone_number_id=%r waba_id=%r business_endpoint=%r",
                    metadata.get("phone_number_id"),
                    waba_id,
                    business_id,
                )
                continue
            if business_id is not None and account.business_id != business_id:
                logger.warning("Ignoring webhook event for business %s on business-specific endpoint %s", account.business_id, business_id)
                continue
            contacts = {contact.get("wa_id"): contact.get("profile", {}).get("name") for contact in value.get("contacts", [])}
            for message in value.get("messages", []):
                text = message.get("text", {}).get("body") or message.get("button", {}).get("text") or message.get("interactive", {}).get("button_reply", {}).get("title") or ""
                if not message.get("id") or not message.get("from"):
                    continue
                events.append(
                    Event(
                        name="message.inbound.created",
                        business_id=account.business_id,
                        payload={
                            "provider_message_id": message.get("id"),
                            "from": message.get("from"),
                            "profile_name": contacts.get(message.get("from")),
                            "type": message.get("type", "text"),
                            "body": text,
                            "raw": {
                                **message,
                                "_metadata": {
                                    "phone_number_id": metadata.get("phone_number_id"),
                                    "display_phone_number": metadata.get("display_phone_number"),
                                    "waba_id": waba_id,
                                },
                            },
                        },
                    )
                )
            for status_payload in value.get("statuses", []):
                events.append(Event(name="message.status.updated", business_id=account.business_id, payload=status_payload))
    return events
