from datetime import datetime

from sqlalchemy.orm import Session

from app import models, schemas
from app.services import ai, knowledge, whatsapp
from app.services.audit import audit


START_COMMANDS = {"setup", "start setup", "onboarding", "start onboarding", "setup my business"}
RESET_COMMANDS = {"restart setup", "reset setup", "redo setup"}
CANCEL_COMMANDS = {"cancel setup", "stop setup", "exit setup"}

QUESTIONS = [
    {
        "key": "business_type",
        "label": "Business type",
        "question": "What type of business is this? For example: clinic, salon, restaurant, ecommerce shop, agency.",
    },
    {
        "key": "services",
        "label": "Services",
        "question": "What services or products do you offer? You can list prices, durations, or categories if useful.",
    },
    {
        "key": "appointments_required",
        "label": "Appointments",
        "question": "Do customers need appointments or bookings? If yes, tell me what information is needed before booking.",
    },
    {
        "key": "inquiry_handling",
        "label": "Inquiry handling",
        "question": "How should common customer questions be handled? Mention FAQs, escalation rules, or anything the bot should never answer.",
    },
    {
        "key": "team_structure",
        "label": "Team",
        "question": "Who is on the team and what are their roles? If there are multiple staff members, list each person and role.",
    },
    {
        "key": "operating_hours",
        "label": "Operating hours",
        "question": "What are your operating hours, holidays, and response-time expectations?",
    },
    {
        "key": "routing_logic",
        "label": "Routing",
        "question": "When should the bot route a customer to a human, a specific team member, or a booking flow?",
    },
    {
        "key": "automations",
        "label": "Automations",
        "question": "What should the bot automate? For example: bookings, order status, reminders, lead capture, support tickets.",
    },
    {
        "key": "other_requirements",
        "label": "Other requirements",
        "question": "Any other business rules, tone preferences, language needs, or special requirements?",
    },
]


def normalized(text: str) -> str:
    return " ".join(text.strip().lower().split())


def active_session(db: Session, inbound: models.Message) -> models.OnboardingSession | None:
    return (
        db.query(models.OnboardingSession)
        .filter(
            models.OnboardingSession.business_id == inbound.business_id,
            models.OnboardingSession.customer_id == inbound.customer_id,
            models.OnboardingSession.status == "active",
        )
        .order_by(models.OnboardingSession.started_at.desc())
        .first()
    )


def start_session(db: Session, inbound: models.Message, reset: bool = False) -> models.OnboardingSession:
    if reset:
        for session in (
            db.query(models.OnboardingSession)
            .filter(
                models.OnboardingSession.business_id == inbound.business_id,
                models.OnboardingSession.customer_id == inbound.customer_id,
                models.OnboardingSession.status == "active",
            )
            .all()
        ):
            session.status = "cancelled"
            session.updated_at = datetime.utcnow()

    session = models.OnboardingSession(
        business_id=inbound.business_id,
        customer_id=inbound.customer_id,
        conversation_id=inbound.conversation_id,
        status="active",
        current_step=0,
        answers_json={},
        generated_config_json={},
    )
    business = db.get(models.Business, inbound.business_id)
    if business:
        business.status = "onboarding"
    db.add(session)
    db.flush()
    return session


def handle_inbound(db: Session, inbound: models.Message) -> bool:
    body = normalized(inbound.body)
    session = active_session(db, inbound)

    if body in CANCEL_COMMANDS and session:
        session.status = "cancelled"
        session.updated_at = datetime.utcnow()
        whatsapp.send_text(db, inbound.business_id, inbound.conversation_id, inbound.customer_id, "Setup cancelled. Send 'setup' anytime to start again.", ai_generated=True)
        return True

    if body in RESET_COMMANDS:
        session = start_session(db, inbound, reset=True)
        send_question(db, inbound, session, include_intro=True)
        return True

    if not session and body not in START_COMMANDS:
        return False

    if not session:
        session = start_session(db, inbound)
        send_question(db, inbound, session, include_intro=True)
        return True

    save_answer(session, inbound.body)
    if session.current_step >= len(QUESTIONS):
        complete_session(db, inbound, session)
    else:
        send_question(db, inbound, session)
    return True


def save_answer(session: models.OnboardingSession, body: str) -> None:
    question = QUESTIONS[session.current_step]
    answer = body.strip()
    answers = dict(session.answers_json or {})
    answers[question["key"]] = "" if normalized(answer) == "skip" else answer
    session.answers_json = answers
    session.current_step += 1
    session.updated_at = datetime.utcnow()


def send_question(db: Session, inbound: models.Message, session: models.OnboardingSession, include_intro: bool = False) -> None:
    question = QUESTIONS[session.current_step]
    progress = f"Question {session.current_step + 1} of {len(QUESTIONS)}"
    intro = ""
    if include_intro:
        intro = (
            "Great, I will set up your business assistant from WhatsApp. "
            "Reply to each question in one message. Send 'skip' if something does not apply, or 'cancel setup' to stop.\n\n"
        )
    whatsapp.send_text(db, inbound.business_id, inbound.conversation_id, inbound.customer_id, f"{intro}{progress}: {question['question']}", ai_generated=True)


def complete_session(db: Session, inbound: models.Message, session: models.OnboardingSession) -> None:
    config = build_config(session.answers_json or {})
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    session.updated_at = datetime.utcnow()
    session.generated_config_json = config

    business = db.get(models.Business, inbound.business_id)
    if business:
        business.industry = config["business_profile"].get("business_type") or business.industry
        business.status = "configured"

    settings = ai.get_settings(db, inbound.business_id)
    settings.tone = config["bot_behavior"]["tone"]
    settings.system_prompt = config["bot_behavior"]["system_prompt"]
    settings.fallback_message = config["bot_behavior"]["fallback_message"]
    settings.handoff_rules_json = config["routing_logic"]
    settings.workflow_config_json = config

    knowledge.create_source(
        db,
        inbound.business_id,
        schemas.KnowledgeSourceCreate(
            type="onboarding",
            title="WhatsApp onboarding profile",
            content=knowledge_text(config),
        ),
    )
    audit(db, business_id=inbound.business_id, action="onboarding.completed", entity_type="onboarding_session", entity_id=str(session.id), actor_type="system", after=config)

    summary = (
        "Setup complete. I configured your assistant with:\n"
        f"- Business type: {config['business_profile'].get('business_type') or 'not specified'}\n"
        f"- Booking flow: {'enabled' if config['workflows']['booking']['enabled'] else 'not enabled'}\n"
        f"- Human routing: {config['routing_logic'].get('human_handoff')}\n\n"
        "You can now test customer messages here."
    )
    whatsapp.send_text(db, inbound.business_id, inbound.conversation_id, inbound.customer_id, summary, ai_generated=True)


def build_config(answers: dict) -> dict:
    appointments = answers.get("appointments_required", "")
    automations = answers.get("automations", "")
    booking_enabled = contains_any(appointments, ["yes", "appointment", "booking", "schedule", "slot"]) or contains_any(automations, ["booking", "appointment", "reminder"])
    language_hint = "bn-BD" if contains_any(answers.get("other_requirements", ""), ["bangla", "bengali", "বাংলা"]) else "en"
    tone = "friendly, professional, concise"

    return {
        "business_profile": {
            "business_type": answers.get("business_type", ""),
            "services": answers.get("services", ""),
            "operating_hours": answers.get("operating_hours", ""),
            "language": language_hint,
        },
        "team": {
            "structure": answers.get("team_structure", ""),
        },
        "customer_journey": {
            "inquiry_handling": answers.get("inquiry_handling", ""),
            "other_requirements": answers.get("other_requirements", ""),
        },
        "routing_logic": {
            "human_handoff": answers.get("routing_logic", "") or "Escalate complaints, refunds, urgent requests, and anything the bot cannot answer confidently.",
            "team_routing": answers.get("team_structure", ""),
        },
        "workflows": {
            "booking": {
                "enabled": booking_enabled,
                "requirements": appointments,
            },
            "automations": automations,
        },
        "bot_behavior": {
            "tone": tone,
            "fallback_message": "I am not fully sure about that yet. I can connect you with a human teammate.",
            "system_prompt": build_system_prompt(answers, booking_enabled, tone),
        },
        "raw_answers": answers,
    }


def build_system_prompt(answers: dict, booking_enabled: bool, tone: str) -> str:
    booking_rule = "Guide customers into the booking flow when they ask for appointments." if booking_enabled else "Do not promise bookings unless the business enables a booking workflow."
    return f"""
You are the WhatsApp assistant for this business.

Business type:
{answers.get('business_type', '')}

Services and products:
{answers.get('services', '')}

Operating hours:
{answers.get('operating_hours', '')}

Customer inquiry handling:
{answers.get('inquiry_handling', '')}

Team and roles:
{answers.get('team_structure', '')}

Routing and escalation:
{answers.get('routing_logic', '')}

Automations:
{answers.get('automations', '')}

Other requirements:
{answers.get('other_requirements', '')}

Rules:
- Use a {tone} tone.
- Keep WhatsApp replies short and clear.
- {booking_rule}
- Ask one clarifying question when required information is missing.
- Escalate to a human when the request matches routing rules or confidence is low.
""".strip()


def knowledge_text(config: dict) -> str:
    profile = config["business_profile"]
    workflows = config["workflows"]
    return "\n\n".join(
        [
            f"Business type: {profile.get('business_type')}",
            f"Services/products: {profile.get('services')}",
            f"Operating hours: {profile.get('operating_hours')}",
            f"Team structure: {config['team'].get('structure')}",
            f"Inquiry handling: {config['customer_journey'].get('inquiry_handling')}",
            f"Human routing: {config['routing_logic'].get('human_handoff')}",
            f"Booking enabled: {workflows['booking'].get('enabled')}",
            f"Booking requirements: {workflows['booking'].get('requirements')}",
            f"Automations: {workflows.get('automations')}",
            f"Other requirements: {config['customer_journey'].get('other_requirements')}",
        ]
    )


def contains_any(text: str, words: list[str]) -> bool:
    lower = text.lower()
    return any(word in lower for word in words)
