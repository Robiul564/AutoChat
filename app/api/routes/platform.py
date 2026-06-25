from fastapi import APIRouter, Depends, Request

from app import schemas
from app.core.config import settings
from app.core.security import get_actor_email
from app.core.url import public_base_url_from_request
from app.core.version import APP_VERSION, SEND_ERROR_FORMAT

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/session")
def session(actor_email: str = Depends(get_actor_email)):
    return {
        "actor_email": actor_email,
        "is_platform_admin": actor_email.lower() in settings.platform_admin_email_set,
    }


@router.get("/version")
def version():
    return {
        "app_version": APP_VERSION,
        "send_error_format": SEND_ERROR_FORMAT,
        "whatsapp_send_mode": settings.whatsapp_send_mode,
        "environment": settings.environment,
    }


@router.get("/webhook-setup", response_model=schemas.WhatsAppWebhookSetupOut)
def webhook_setup(request: Request):
    public_base_url = public_base_url_from_request(request)
    callback_url = f"{public_base_url}/webhooks/meta/whatsapp"
    return {
        "callback_url": callback_url,
        "verify_token": settings.webhook_verify_token,
        "send_mode": settings.whatsapp_send_mode,
        "graph_api_url": settings.whatsapp_graph_api_url,
        "is_public_url": public_base_url.startswith("https://"),
    }
