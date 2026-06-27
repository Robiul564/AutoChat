from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings
from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access, require_platform_admin
from app.core.url import public_base_url_from_request
from app.services import whatsapp

router = APIRouter(prefix="/api/businesses/{business_id}/whatsapp/accounts", tags=["whatsapp"])


@router.get("", response_model=list[schemas.WhatsAppAccountOut])
def list_accounts(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return (
        db.query(models.WhatsAppAccount)
        .filter(models.WhatsAppAccount.business_id == business_id)
        .order_by(models.WhatsAppAccount.created_at.desc())
        .all()
    )


@router.get("/webhook-setup", response_model=schemas.WhatsAppWebhookSetupOut)
def webhook_setup(business_id: int, request: Request, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    callback_path = f"/webhooks/meta/whatsapp/business/{business_id}"
    public_base_url = public_base_url_from_request(request)
    callback_url = f"{public_base_url}{callback_path}"
    return {
        "callback_url": callback_url,
        "verify_token": whatsapp.webhook_verify_token_for_business(business_id),
        "send_mode": settings.whatsapp_send_mode,
        "graph_api_url": settings.whatsapp_graph_api_url,
        "is_public_url": public_base_url.startswith("https://"),
    }

@router.post("", response_model=schemas.WhatsAppAccountOut)
def save_account(business_id: int, payload: schemas.WhatsAppAccountCreate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    return whatsapp.save_account(db, business_id, payload)


@router.post("/{account_id}/validate")
def validate_account(business_id: int, account_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    account = db.query(models.WhatsAppAccount).filter(models.WhatsAppAccount.business_id == business_id, models.WhatsAppAccount.id == account_id).one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp account not found")
    return whatsapp.validate_account(db, account)


@router.post("/{account_id}/rotate-token", response_model=schemas.WhatsAppAccountOut)
def rotate_token(business_id: int, account_id: int, payload: schemas.TokenRotate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    account = db.query(models.WhatsAppAccount).filter(models.WhatsAppAccount.business_id == business_id, models.WhatsAppAccount.id == account_id).one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp account not found")
    return whatsapp.rotate_token(db, account, payload)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(business_id: int, account_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    account = db.query(models.WhatsAppAccount).filter(models.WhatsAppAccount.business_id == business_id, models.WhatsAppAccount.id == account_id).one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp account not found")
    whatsapp.delete_account(db, account)
