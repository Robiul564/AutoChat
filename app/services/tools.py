from datetime import datetime
from uuid import uuid5, NAMESPACE_URL

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.services.audit import audit
from app.services.secrets import store_secret


CATALOG = [
    {
        "key": "calendar.basic",
        "provider": "Mock Calendar",
        "name": "Calendar Booking",
        "description": "Check availability and create simple booking holds.",
        "action_schema_json": {
            "actions": {
                "check_availability": {"required": ["date"]},
                "create_booking": {"required": ["date", "name"]},
            }
        },
        "auth_type": "api_key",
    }
]


def seed_tools(db: Session) -> None:
    for item in CATALOG:
        existing = db.query(models.Tool).filter(models.Tool.key == item["key"]).one_or_none()
        if not existing:
            db.add(models.Tool(**item, status="active"))
    db.commit()


def enable_tool(db: Session, business_id: int, payload: schemas.ToolEnable) -> models.BusinessTool:
    tool = db.get(models.Tool, payload.tool_id)
    if not tool or tool.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    credential = store_secret(db, business_id, f"tool_{tool.key}_credential", payload.credential) if payload.credential else None
    business_tool = models.BusinessTool(
        business_id=business_id,
        tool_id=tool.id,
        name=payload.name or tool.name,
        enabled=True,
        config_json=payload.config,
        credential_secret_id=credential.id if credential else None,
        policy_json=payload.policy,
    )
    db.add(business_tool)
    audit(db, business_id=business_id, action="tool.enabled", entity_type="business_tool", entity_id=tool.key, after=payload.model_dump())
    db.commit()
    db.refresh(business_tool)
    return business_tool


def execute_tool(
    db: Session,
    business_id: int,
    business_tool_id: int,
    action: str,
    input_json: dict,
    conversation_id: int | None = None,
    message_id: int | None = None,
) -> models.ToolExecution:
    business_tool = (
        db.query(models.BusinessTool)
        .filter(models.BusinessTool.id == business_tool_id, models.BusinessTool.business_id == business_id)
        .one_or_none()
    )
    if not business_tool or not business_tool.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enabled business tool not found")
    idempotency_key = str(uuid5(NAMESPACE_URL, f"{business_id}:{business_tool_id}:{action}:{input_json}"))
    existing = (
        db.query(models.ToolExecution)
        .filter(models.ToolExecution.business_id == business_id, models.ToolExecution.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    execution = models.ToolExecution(
        business_id=business_id,
        conversation_id=conversation_id,
        message_id=message_id,
        business_tool_id=business_tool.id,
        action=action,
        input_json=input_json,
        idempotency_key=idempotency_key,
        status="running",
    )
    db.add(execution)
    db.flush()
    try:
        execution.output_json = run_mock_action(action, input_json)
        execution.status = "succeeded"
    except Exception as exc:
        execution.status = "failed"
        execution.error_json = {"message": str(exc)}
    execution.finished_at = datetime.utcnow()
    audit(db, business_id=business_id, action="tool.executed", entity_type="tool_execution", entity_id=str(execution.id), actor_type="system", after={"status": execution.status})
    db.commit()
    db.refresh(execution)
    return execution


def run_mock_action(action: str, input_json: dict) -> dict:
    if action == "check_availability":
        return {"available": True, "slots": ["10:00", "14:30", "17:00"], "date": input_json.get("date")}
    if action == "create_booking":
        return {"booking_id": f"bk_{uuid5(NAMESPACE_URL, str(input_json)).hex[:10]}", "status": "held", "input": input_json}
    raise ValueError(f"Unsupported action: {action}")
