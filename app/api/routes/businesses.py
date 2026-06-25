from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access, require_platform_admin
from app.services import tenant

router = APIRouter(prefix="/api/businesses", tags=["businesses"])


@router.post("", response_model=schemas.BusinessOut)
def create_business(payload: schemas.BusinessCreate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    return tenant.create_business(db, payload, actor_email)


@router.get("", response_model=list[schemas.BusinessOut])
def list_businesses(db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    user = db.query(models.User).filter(models.User.email == actor_email).one_or_none()
    if not user:
        return []
    return (
        db.query(models.Business)
        .join(models.BusinessUser, models.BusinessUser.business_id == models.Business.id)
        .filter(models.BusinessUser.user_id == user.id, models.BusinessUser.status == "active")
        .order_by(models.Business.created_at.desc())
        .all()
    )


@router.get("/{business_id}", response_model=schemas.BusinessOut)
def get_business(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    return require_business_access(db, business_id, actor_email)


@router.patch("/{business_id}", response_model=schemas.BusinessOut)
def update_business(business_id: int, payload: schemas.BusinessUpdate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    business = require_business_access(db, business_id, actor_email)
    return tenant.update_business(db, business, payload)


@router.post("/{business_id}/suspend", response_model=schemas.BusinessOut)
def suspend_business(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    business = require_business_access(db, business_id, actor_email)
    business.status = "suspended"
    db.commit()
    db.refresh(business)
    return business
