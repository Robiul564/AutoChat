from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app import models, schemas
from app.core.config import settings
from app.core.security import derive_slug
from app.services.audit import audit


def ensure_user(db: Session, email: str, name: str | None = None) -> models.User:
    user = db.query(models.User).filter(models.User.email == email).one_or_none()
    if user:
        return user
    user = models.User(email=email, name=name or email.split("@")[0])
    db.add(user)
    db.flush()
    return user


def unique_slug(db: Session, name: str) -> str:
    base = derive_slug(name)
    slug = base
    suffix = 2
    while db.query(models.Business).filter(models.Business.slug == slug).first():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def create_business(db: Session, payload: schemas.BusinessCreate, actor_email: str) -> models.Business:
    user = ensure_user(db, actor_email)
    existing = (
        db.query(models.Business)
        .join(models.BusinessUser, models.BusinessUser.business_id == models.Business.id)
        .filter(
            models.BusinessUser.user_id == user.id,
            models.BusinessUser.status == "active",
            func.lower(models.Business.name) == payload.name.strip().lower(),
        )
        .one_or_none()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This business already exists for this owner")
    business = models.Business(
        name=payload.name.strip(),
        slug=unique_slug(db, payload.name.strip()),
        industry=payload.industry,
        timezone=payload.timezone,
        locale=payload.locale,
        plan_id=payload.plan_id,
        status="profile_complete",
    )
    db.add(business)
    db.flush()
    db.add(models.BusinessUser(business_id=business.id, user_id=user.id, role="owner"))
    db.add(
        models.AISettings(
            business_id=business.id,
            model_provider=settings.ai_model_provider,
            model_name=settings.ai_model_name,
            system_prompt=f"You are the WhatsApp assistant for {business.name}.",
        )
    )
    audit(db, business_id=business.id, actor_user_id=user.id, action="business.created", entity_type="business", entity_id=str(business.id))
    db.commit()
    db.refresh(business)
    return business


def update_business(db: Session, business: models.Business, payload: schemas.BusinessUpdate) -> models.Business:
    before = {
        "name": business.name,
        "industry": business.industry,
        "timezone": business.timezone,
        "locale": business.locale,
        "status": business.status,
        "plan_id": business.plan_id,
    }
    update = payload.model_dump(exclude_unset=True)
    new_name = update.get("name")
    if new_name is not None:
        new_name = new_name.strip()
        if not new_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Business name cannot be empty")
        owner_ids = db.query(models.BusinessUser.user_id).filter(
            models.BusinessUser.business_id == business.id,
            models.BusinessUser.status == "active",
        )
        duplicate = (
            db.query(models.Business)
            .join(models.BusinessUser, models.BusinessUser.business_id == models.Business.id)
            .filter(
                models.Business.id != business.id,
                models.BusinessUser.user_id.in_(owner_ids),
                models.BusinessUser.status == "active",
                func.lower(models.Business.name) == new_name.lower(),
            )
            .one_or_none()
        )
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This business already exists for this owner")
        update["name"] = new_name
        if new_name != business.name:
            business.slug = unique_slug(db, new_name)
    for key, value in update.items():
        setattr(business, key, value)
    audit(db, business_id=business.id, action="business.updated", entity_type="business", entity_id=str(business.id), before=before, after=update)
    db.commit()
    db.refresh(business)
    return business


def delete_business(db: Session, business: models.Business) -> None:
    business_id = business.id
    db.query(models.ToolExecution).filter(models.ToolExecution.business_id == business_id).delete(synchronize_session=False)
    db.query(models.OnboardingSession).filter(models.OnboardingSession.business_id == business_id).delete(synchronize_session=False)
    db.query(models.MessageStatusEvent).filter(models.MessageStatusEvent.business_id == business_id).delete(synchronize_session=False)
    db.query(models.Message).filter(models.Message.business_id == business_id).delete(synchronize_session=False)
    db.query(models.Conversation).filter(models.Conversation.business_id == business_id).delete(synchronize_session=False)
    db.query(models.Customer).filter(models.Customer.business_id == business_id).delete(synchronize_session=False)
    db.query(models.KnowledgeChunk).filter(models.KnowledgeChunk.business_id == business_id).delete(synchronize_session=False)
    db.query(models.KnowledgeSource).filter(models.KnowledgeSource.business_id == business_id).delete(synchronize_session=False)
    db.query(models.BusinessTool).filter(models.BusinessTool.business_id == business_id).delete(synchronize_session=False)
    db.query(models.WhatsAppAccount).filter(models.WhatsAppAccount.business_id == business_id).delete(synchronize_session=False)
    db.query(models.AISettings).filter(models.AISettings.business_id == business_id).delete(synchronize_session=False)
    db.query(models.Secret).filter(models.Secret.business_id == business_id).delete(synchronize_session=False)
    db.query(models.AuditLog).filter(models.AuditLog.business_id == business_id).delete(synchronize_session=False)
    db.query(models.BusinessUser).filter(models.BusinessUser.business_id == business_id).delete(synchronize_session=False)
    db.delete(business)
    db.commit()
