from fastapi import APIRouter, Depends, Request

from app import schemas
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine, ensure_runtime_schema
from app.core.security import get_actor_email, require_platform_admin
from app.core.url import public_base_url_from_request
from app.services.tools import seed_tools

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/session")
def session(actor_email: str = Depends(get_actor_email)):
    return {
        "actor_email": actor_email,
        "is_platform_admin": actor_email.lower() in settings.platform_admin_email_set,
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

@router.post("/admin/reset-database")
def reset_database(actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        seed_tools(db)
    finally:
        db.close()
    return {"ok": True, "message": "Database reset complete"}
