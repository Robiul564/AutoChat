from fastapi import APIRouter, Depends, Request

from app import schemas
from app.core.config import settings
from app.core.security import get_actor_email

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/session")
def session(actor_email: str = Depends(get_actor_email)):
    return {
        "actor_email": actor_email,
        "is_platform_admin": actor_email.lower() in settings.platform_admin_email_set,
    }


@router.get("/webhook-setup", response_model=schemas.WhatsAppWebhookSetupOut)
def webhook_setup(request: Request):
    public_base_url = settings.public_base_url.rstrip("/")
    callback_url = f"{public_base_url}/webhooks/meta/whatsapp" if public_base_url else str(request.url_for("receive_webhook"))
    return {
        "callback_url": callback_url,
        "verify_token": settings.webhook_verify_token,
        "send_mode": settings.whatsapp_send_mode,
        "graph_api_url": settings.whatsapp_graph_api_url,
        "is_public_url": bool(public_base_url),
    }
