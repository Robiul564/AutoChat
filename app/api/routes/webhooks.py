from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app import schemas
from app.core.config import settings
from app.core.db import get_db
from app.core.security import verify_meta_signature
from app.services import whatsapp
from app.workers.queue import Event, event_queue

router = APIRouter(prefix="/webhooks/meta/whatsapp", tags=["webhooks"])


@router.get("")
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.webhook_verify_token and hub_challenge:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook challenge rejected")


@router.post("", response_model=schemas.WebhookAccepted)
async def receive_webhook(request: Request, db: Session = Depends(get_db), _: None = Depends(verify_meta_signature)):
    payload = await request.json()
    accepted = 0
    for item in extract_events(payload, db):
        await event_queue.publish(item)
        accepted += 1
    return {"accepted": True, "events": accepted}


def extract_events(payload: dict[str, Any], db: Session) -> list[Event]:
    events: list[Event] = []
    for entry in payload.get("entry", []):
        waba_id = str(entry.get("id")) if entry.get("id") else None
        for change in entry.get("changes", []):
            value = change.get("value", {})
            account = whatsapp.resolve_tenant(db, value.get("metadata", {}), waba_id=waba_id)
            if not account:
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
                            "raw": message,
                        },
                    )
                )
            for status_payload in value.get("statuses", []):
                events.append(Event(name="message.status.updated", business_id=account.business_id, payload=status_payload))
    return events
