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
    before = {"name": business.name, "status": business.status}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(business, key, value)
    audit(db, business_id=business.id, action="business.updated", entity_type="business", entity_id=str(business.id), before=before, after=payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(business)
    return business
