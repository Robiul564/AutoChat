from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BusinessCreate(BaseModel):
    name: str
    industry: str | None = None
    timezone: str = "UTC"
    locale: str = "en"
    plan_id: str = "starter"


class BusinessUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    timezone: str | None = None
    locale: str | None = None
    status: str | None = None


class BusinessOut(BaseModel):
    id: int
    name: str
    slug: str
    industry: str | None
    timezone: str
    locale: str
    status: str
    plan_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WhatsAppAccountCreate(BaseModel):
    app_id: str
    app_secret: str
    access_token: str
    phone_number_id: str
    waba_id: str | None = None
    display_phone_number: str | None = None
    webhook_verify_token: str | None = None
    token_expires_at: datetime | None = None


class WhatsAppAccountOut(BaseModel):
    id: int
    business_id: int
    app_id: str
    phone_number_id: str
    waba_id: str | None
    display_phone_number: str | None
    status: str
    last_validated_at: datetime | None

    model_config = {"from_attributes": True}


class WhatsAppWebhookSetupOut(BaseModel):
    callback_url: str
    verify_token: str
    send_mode: str
    graph_api_url: str
    is_public_url: bool


class TokenRotate(BaseModel):
    access_token: str
    expires_at: datetime | None = None


class KnowledgeSourceCreate(BaseModel):
    type: str = "faq"
    title: str
    content: str
    source_uri: str | None = None


class KnowledgeSourceOut(BaseModel):
    id: int
    business_id: int
    type: str
    title: str
    status: str
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeChunkOut(BaseModel):
    id: int
    source_id: int
    content: str
    score: float
    metadata: dict[str, Any]


class MessageCreate(BaseModel):
    body: str
    type: str = "text"


class MessageOut(BaseModel):
    id: int
    business_id: int
    conversation_id: int
    customer_id: int
    direction: str
    type: str
    body: str
    provider_message_id: str | None
    provider_status: str | None
    ai_generated: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    business_id: int
    customer_id: int
    channel: str
    status: str
    ai_enabled: bool
    language: str | None
    last_message_at: datetime | None
    summary: str | None
    created_at: datetime
    customer_name: str | None = None
    customer_phone: str | None = None
    last_message_body: str | None = None

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class HandoffRequest(BaseModel):
    assigned_user_id: int | None = None


class AISettingsUpdate(BaseModel):
    system_prompt: str | None = None
    tone: str | None = None
    fallback_message: str | None = None


class AISettingsOut(BaseModel):
    id: int
    business_id: int
    system_prompt: str
    tone: str
    fallback_message: str
    workflow_config_json: dict[str, Any]

    model_config = {"from_attributes": True}


class OnboardingSessionOut(BaseModel):
    id: int
    business_id: int
    customer_id: int
    conversation_id: int
    status: str
    current_step: int
    answers_json: dict[str, Any]
    generated_config_json: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ToolEnable(BaseModel):
    tool_id: int
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    credential: str | None = None
    policy: dict[str, Any] = Field(default_factory=dict)


class BusinessToolUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None


class ToolExecutionRequest(BaseModel):
    action: str
    input: dict[str, Any] = Field(default_factory=dict)


class WebhookAccepted(BaseModel):
    accepted: bool
    events: int
