# AI WhatsApp SaaS MVP

This repo is a runnable MVP implementation of `AI_WHATSAPP_SAAS_ARCHITECTURE.md`.

It includes:

- Tenant-scoped FastAPI backend.
- SQLite by default, PostgreSQL-ready through `DATABASE_URL`.
- WhatsApp account storage, credential secret wrapping, webhook challenge and inbound routing.
- In-process async queue for webhook/event processing.
- Conversation, customer, message, status, knowledge, tool, AI settings, audit, and analytics APIs.
- Mock AI orchestrator with tenant settings, conversation history, knowledge retrieval, handoff detection, and tool execution hooks.
- Lightweight admin UI served at `/`.

## Database Schema

For the SQLite MVP, use the built-in ORM schema in `app/models.py`. You do not need to create tables by hand.

The app reads this default database URL:

```env
DATABASE_URL=sqlite:///./data/app.db
```

On startup, `app/main.py` calls `Base.metadata.create_all(bind=engine)`, so SQLite creates the tables inside `data/app.db` automatically. The main schema tables are:

- `businesses`, `users`, `business_users`
- `whatsapp_accounts`, `secrets`
- `customers`, `conversations`, `messages`, `message_status_events`
- `knowledge_sources`, `knowledge_chunks`
- `ai_settings`
- `tools`, `business_tools`, `tool_executions`
- `audit_logs`

For production PostgreSQL later, point `DATABASE_URL` to Postgres and add migrations with Alembic.

For Supabase, use the setup guide in `SUPABASE_SETUP.md`.

To initialize the configured database without starting the web server:

```powershell
python scripts/init_db.py
```

## OpenAI Setup

Create a local `.env` from `.env.example`, then set:

```env
AI_MODEL_PROVIDER=openai
AI_MODEL_NAME=gpt-5.5
OPENAI_API_KEY=sk-your-openai-api-key
PLATFORM_ADMIN_EMAILS=owner@example.com
```

The app uses the OpenAI Responses API through the official Python SDK when `AI_MODEL_PROVIDER=openai`. If the key is missing, the API returns a clear configuration error.

## Managed Service Mode

This project is set up for a service-owner model: you run the WhatsApp bot platform for clients on their behalf.

Platform-admin actions:

- Create and suspend businesses.
- Connect WhatsApp credentials.
- Validate or rotate WhatsApp tokens.
- Enable, configure, and test external tools.
- Choose `AI_MODEL_PROVIDER`, `AI_MODEL_NAME`, and `OPENAI_API_KEY` in `.env`.

Client-safe actions:

- View assigned businesses.
- Manage knowledge base content.
- Use the inbox and send agent replies.
- Update bot behavior text: tone, bot instructions, and fallback message.
- View analytics.

Set platform admins in `.env`:

```env
PLATFORM_ADMIN_EMAILS=owner@example.com,admin2@example.com
```

The current MVP uses the `X-User-Email` header / Actor field as a simple local development identity. Before production, replace that with real authentication and memberships.

## Run

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Quick API Flow

1. Create a business:

```bash
curl -X POST http://127.0.0.1:8000/api/businesses \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Demo Clinic\",\"industry\":\"Healthcare\",\"timezone\":\"Asia/Dhaka\",\"locale\":\"bn-BD\"}"
```

2. Save WhatsApp credentials:

```bash
curl -X POST http://127.0.0.1:8000/api/businesses/1/whatsapp/accounts \
  -H "Content-Type: application/json" \
  -d "{\"app_id\":\"YOUR_META_APP_ID\",\"app_secret\":\"YOUR_META_APP_SECRET\",\"access_token\":\"YOUR_WHATSAPP_CLOUD_API_ACCESS_TOKEN\",\"phone_number_id\":\"YOUR_PHONE_NUMBER_ID\",\"waba_id\":\"YOUR_WHATSAPP_BUSINESS_ACCOUNT_ID\",\"display_phone_number\":\"+8801000000000\"}"
```

3. Simulate a webhook:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/meta/whatsapp \
  -H "Content-Type: application/json" \
  -d "{\"entry\":[{\"id\":\"YOUR_WHATSAPP_BUSINESS_ACCOUNT_ID\",\"changes\":[{\"value\":{\"metadata\":{\"phone_number_id\":\"YOUR_PHONE_NUMBER_ID\",\"display_phone_number\":\"+8801000000000\"},\"messages\":[{\"id\":\"wamid.demo1\",\"from\":\"8801711111111\",\"timestamp\":\"1781770000\",\"type\":\"text\",\"text\":{\"body\":\"What are your hours?\"}}]}}]}]}"
```

## Notes

This is intentionally an MVP. Production hardening should replace the in-process queue with Redis/RabbitMQ/Kafka, replace the mock AI gateway with a real provider, add migrations, and use real KMS/Vault envelope encryption.
