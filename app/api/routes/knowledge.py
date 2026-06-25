from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access
from app.services import knowledge

router = APIRouter(prefix="/api/businesses/{business_id}/knowledge", tags=["knowledge"])


@router.post("/sources", response_model=schemas.KnowledgeSourceOut)
def create_source(business_id: int, payload: schemas.KnowledgeSourceCreate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    user = db.query(models.User).filter(models.User.email == actor_email).one_or_none()
    return knowledge.create_source(db, business_id, payload, created_by=user.id if user else None)


@router.get("/sources", response_model=list[schemas.KnowledgeSourceOut])
def list_sources(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return db.query(models.KnowledgeSource).filter(models.KnowledgeSource.business_id == business_id).order_by(models.KnowledgeSource.created_at.desc()).all()


@router.get("/sources/{source_id}", response_model=schemas.KnowledgeSourceOut)
def get_source(business_id: int, source_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    source = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.business_id == business_id, models.KnowledgeSource.id == source_id).one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    return source


@router.post("/sources/{source_id}/reingest")
def reingest_source(business_id: int, source_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    source = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.business_id == business_id, models.KnowledgeSource.id == source_id).one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    source.status = "ready"
    source.version += 1
    db.commit()
    return {"job": "inline-reingest", "source_id": source_id, "status": source.status}


@router.delete("/sources/{source_id}")
def delete_source(business_id: int, source_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    source = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.business_id == business_id, models.KnowledgeSource.id == source_id).one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    db.query(models.KnowledgeChunk).filter(models.KnowledgeChunk.business_id == business_id, models.KnowledgeChunk.source_id == source_id).delete()
    db.delete(source)
    db.commit()
    return {"deleted": True}


@router.post("/search", response_model=list[schemas.KnowledgeChunkOut])
def search_knowledge(business_id: int, payload: schemas.KnowledgeSearchRequest, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return knowledge.search(db, business_id, payload.query, payload.top_k)
