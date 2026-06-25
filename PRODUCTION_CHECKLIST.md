# Production Checklist

This app is now production-hardened enough for a staging launch, but use this checklist before real customers.

## Required Environment

```env
APP_ENV=production
DATABASE_URL=postgresql+psycopg://...
APP_SECRET=strong-random-32-plus-chars
AUTH_MODE=admin_key
ADMIN_API_KEY=strong-random-24-plus-chars
PLATFORM_ADMIN_EMAILS=owner@example.com
PUBLIC_BASE_URL=https://your-domain.example
WEBHOOK_VERIFY_TOKEN=strong-random-token
ALLOWED_ORIGINS=https://your-domain.example
ALLOWED_HOSTS=your-domain.example
ENABLE_DOCS=false
WHATSAPP_SEND_MODE=mock
```

Switch to live sending only after webhook receive and routing are verified:

```env
WHATSAPP_SEND_MODE=live
META_APP_SECRET=your-meta-app-secret
```

Use OpenAI only after setting a real key:

```env
AI_MODEL_PROVIDER=openai
AI_MODEL_NAME=gpt-5.5
OPENAI_API_KEY=sk-...
```

## Must Pass

- `python scripts/production_check.py`
- `python scripts/init_db.py`
- `python -m py_compile app/main.py app/core/config.py app/core/security.py`
- Frontend loads from the deployed URL.
- `/api/platform/session` returns 200 with `X-Admin-Key`.
- Meta webhook verify succeeds.
- A test inbound WhatsApp webhook creates the correct business conversation.
- A second business does not see the first business's conversations or knowledge.

## Known Limits To Replace Later

- `AUTH_MODE=admin_key` is a staging-grade admin gate, not full user authentication.
- SQLite is for local development only.
- Inline table creation is acceptable for staging; add Alembic migrations before larger production use.
- The in-process event queue is fine for low traffic; replace with Redis/RabbitMQ/Kafka when traffic grows.
