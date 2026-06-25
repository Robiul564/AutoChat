from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.core.security import get_actor_email, require_business_access, require_platform_admin
from app.services import tools as tool_service

router = APIRouter(tags=["tools"])


@router.get("/api/tools/catalog")
def catalog(db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    return db.query(models.Tool).filter(models.Tool.status == "active").all()


@router.post("/api/businesses/{business_id}/tools")
def enable_tool(business_id: int, payload: schemas.ToolEnable, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    return tool_service.enable_tool(db, business_id, payload)


@router.post("/api/businesses/{business_id}/tools/{business_tool_id}/auth/start")
def start_auth(business_id: int, business_tool_id: int, redirect_uri: str | None = None, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    business_tool = db.query(models.BusinessTool).filter(models.BusinessTool.business_id == business_id, models.BusinessTool.id == business_tool_id).one_or_none()
    if not business_tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business tool not found")
    return {"auth_url": redirect_uri or "mock://tool-auth/complete", "session": f"tool-{business_tool_id}"}


@router.post("/api/businesses/{business_id}/tools/{business_tool_id}/test")
def test_tool(business_id: int, business_tool_id: int, payload: schemas.ToolExecutionRequest, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    return tool_service.execute_tool(db, business_id, business_tool_id, payload.action, payload.input)


@router.patch("/api/businesses/{business_id}/tools/{business_tool_id}")
def update_business_tool(business_id: int, business_tool_id: int, payload: schemas.BusinessToolUpdate, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_platform_admin(actor_email)
    require_business_access(db, business_id, actor_email)
    business_tool = db.query(models.BusinessTool).filter(models.BusinessTool.business_id == business_id, models.BusinessTool.id == business_tool_id).one_or_none()
    if not business_tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business tool not found")
    data = payload.model_dump(exclude_unset=True)
    if "config" in data:
        business_tool.config_json = data.pop("config")
    if "policy" in data:
        business_tool.policy_json = data.pop("policy")
    for key, value in data.items():
        setattr(business_tool, key, value)
    db.commit()
    db.refresh(business_tool)
    return business_tool


@router.get("/api/businesses/{business_id}/tools/executions")
def executions(business_id: int, db: Session = Depends(get_db), actor_email: str = Depends(get_actor_email)):
    require_business_access(db, business_id, actor_email)
    return db.query(models.ToolExecution).filter(models.ToolExecution.business_id == business_id).order_by(models.ToolExecution.started_at.desc()).all()
