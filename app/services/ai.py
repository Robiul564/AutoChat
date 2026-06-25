from dataclasses import dataclass
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.core.config import settings as app_settings
from app.services import knowledge, tools, whatsapp

logger = logging.getLogger(__name__)


@dataclass
class ResponsePlan:
    reply_text: str
    actions: list[dict]
    confidence: float
    handoff_required: bool


HANDOFF_WORDS = {"human", "agent", "complaint", "refund", "angry", "manager"}


def get_settings(db: Session, business_id: int) -> models.AISettings:
    settings = db.query(models.AISettings).filter(models.AISettings.business_id == business_id).one_or_none()
    if settings:
        if settings.model_provider != app_settings.ai_model_provider or settings.model_name != app_settings.ai_model_name:
            settings.model_provider = app_settings.ai_model_provider
            settings.model_name = app_settings.ai_model_name
            db.commit()
            db.refresh(settings)
        return settings
    settings = models.AISettings(
        business_id=business_id,
        model_provider=app_settings.ai_model_provider,
        model_name=app_settings.ai_model_name,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def build_response_plan(db: Session, inbound: models.Message) -> ResponsePlan:
    business = db.get(models.Business, inbound.business_id)
    settings = get_settings(db, inbound.business_id)
    body = inbound.body.strip()
    lower = body.lower()
    hits = knowledge.search(db, inbound.business_id, body, top_k=3)
    handoff = any(word in lower for word in HANDOFF_WORDS)
    actions: list[dict] = []

    if handoff:
        reply = "I understand. I am handing this to a human teammate now."
        confidence = 0.8
    elif "book" in lower or "appointment" in lower:
        business_tool = (
            db.query(models.BusinessTool)
            .filter(models.BusinessTool.business_id == inbound.business_id, models.BusinessTool.enabled.is_(True))
            .first()
        )
        if business_tool:
            result = tools.execute_tool(
                db,
                inbound.business_id,
                business_tool.id,
                "check_availability",
                {"date": "next_available"},
                conversation_id=inbound.conversation_id,
                message_id=inbound.id,
            )
            actions.append({"tool_execution_id": result.id, "status": result.status, "output": result.output_json})
            slots = ", ".join(result.output_json.get("slots", []))
            reply = f"I can help with that. Available slots are {slots}. Which one should I hold for you?"
            confidence = 0.86
        else:
            reply = "I can help with bookings, but this business has not enabled a booking tool yet."
            confidence = 0.55
    elif should_use_openai(settings):
        try:
            reply = generate_openai_reply(db, inbound, business, settings, hits)
            confidence = 0.82 if hits else 0.62
        except Exception as exc:
            logger.exception("OpenAI reply generation failed for business=%s conversation=%s", inbound.business_id, inbound.conversation_id)
            reply = fallback_reply(business, settings, hits)
            confidence = 0.45 if hits else 0.25
    elif hits:
        citation = hits[0]["metadata"].get("title", "your knowledge base")
        reply = f"{hits[0]['content']}\n\nSource: {citation}"
        confidence = max(0.5, min(0.95, hits[0]["score"]))
    elif business:
        reply = f"Thanks for messaging {business.name}. {settings.fallback_message}"
        confidence = 0.35
    else:
        reply = settings.fallback_message
        confidence = 0.25

    return ResponsePlan(reply_text=reply, actions=actions, confidence=confidence, handoff_required=handoff)


def should_use_openai(settings: models.AISettings) -> bool:
    provider = (settings.model_provider or app_settings.ai_model_provider).lower()
    if provider == "openai":
        return True
    if provider == "auto":
        return bool(app_settings.openai_api_key)
    if app_settings.is_production and app_settings.openai_api_key and provider == "mock":
        return True
    return False


def fallback_reply(business: models.Business | None, settings: models.AISettings, hits: list[dict]) -> str:
    if hits:
        citation = hits[0]["metadata"].get("title", "your knowledge base")
        return f"{hits[0]['content']}\n\nSource: {citation}"
    if business:
        return f"Thanks for messaging {business.name}. {settings.fallback_message}"
    return settings.fallback_message


def generate_openai_reply(
    db: Session,
    inbound: models.Message,
    business: models.Business | None,
    settings: models.AISettings,
    hits: list[dict],
) -> str:
    if not app_settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY is not configured",
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI SDK is not installed. Run pip install -r requirements.txt",
        ) from exc

    recent = (
        db.query(models.Message)
        .filter(
            models.Message.business_id == inbound.business_id,
            models.Message.conversation_id == inbound.conversation_id,
        )
        .order_by(models.Message.created_at.desc())
        .limit(8)
        .all()
    )
    recent.reverse()
    knowledge_text = "\n\n".join(
        f"[{idx + 1}] {hit['metadata'].get('title', 'Knowledge')}: {hit['content']}"
        for idx, hit in enumerate(hits)
    ) or "No matching tenant knowledge was found."
    history_text = "\n".join(f"{msg.direction}: {msg.body}" for msg in recent)
    business_name = business.name if business else "this business"
    prompt = f"""
Business: {business_name}
Industry: {business.industry if business else "unknown"}
Timezone: {business.timezone if business else "UTC"}
Locale: {business.locale if business else "en"}
Tone: {settings.tone}

System instructions:
{settings.system_prompt}

Rules:
- Answer as a WhatsApp business assistant.
- Use only the tenant knowledge below and the conversation history.
- If the answer is not supported, ask a short clarifying question or offer human handoff.
- Keep the reply concise and customer-facing.

Tenant knowledge:
{knowledge_text}

Recent conversation:
{history_text}

Customer message:
{inbound.body}
""".strip()

    client = OpenAI(api_key=app_settings.openai_api_key)
    model_name = settings.model_name if settings.model_name != "local-mock" else app_settings.ai_model_name
    response = client.responses.create(
        model=model_name,
        input=[
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": "You generate safe, concise WhatsApp replies for one tenant at a time."}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
    )
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()
    return settings.fallback_message


def respond_to_inbound(db: Session, inbound: models.Message) -> models.Message | None:
    conversation = db.get(models.Conversation, inbound.conversation_id)
    if not conversation or not conversation.ai_enabled:
        return None
    plan = build_response_plan(db, inbound)
    if plan.handoff_required:
        conversation.status = "pending_handoff"
        db.commit()
    return whatsapp.send_text(db, inbound.business_id, inbound.conversation_id, inbound.customer_id, plan.reply_text, ai_generated=True)
