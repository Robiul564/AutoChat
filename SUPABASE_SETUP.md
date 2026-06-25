# Supabase Setup

This app can use Supabase because Supabase gives you a normal PostgreSQL database.

## 1. Create A Supabase Project

Create a project in Supabase, then open:

```text
Project Dashboard -> Connect
```

Copy a Postgres connection string.

## 2. Pick The Right Connection String

For local development on Windows, use **Session pooler** first. It works on IPv4 networks and is best for a persistent backend app.

Example:

```env
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:YOUR_DB_PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

Supabase sometimes shows Prisma instructions like:

```env
DATABASE_URL="postgresql://postgres.qauecdpocczgotejiekk:YOUR_DB_PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true"
DIRECT_URL="postgresql://postgres.qauecdpocczgotejiekk:YOUR_DB_PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
```

For this Python/FastAPI app, do not install Prisma. Use the SQLAlchemy equivalent:

```env
DATABASE_URL=postgresql+psycopg://postgres.qauecdpocczgotejiekk:YOUR_DB_PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
DIRECT_URL=postgresql+psycopg://postgres.qauecdpocczgotejiekk:YOUR_DB_PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

Direct connection also works if your network supports IPv6 or your Supabase project has the IPv4 add-on:

```env
DATABASE_URL=postgresql+psycopg://postgres:YOUR_DB_PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
```

Avoid transaction pooler for this MVP unless you know you need it:

```env
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:YOUR_DB_PASSWORD@aws-REGION.pooler.supabase.com:6543/postgres?sslmode=require
```

## 3. Create `.env`

Create a file named `.env` in the project root:

```env
APP_NAME=AI WhatsApp SaaS
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:YOUR_DB_PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres?sslmode=require
DIRECT_URL=postgresql+psycopg://postgres.PROJECT_REF:YOUR_DB_PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
APP_SECRET=replace-me-with-a-long-random-secret
PLATFORM_ADMIN_EMAILS=owner@example.com
META_APP_SECRET=
WEBHOOK_VERIFY_TOKEN=platform-dev-token
AI_MODEL_PROVIDER=openai
AI_MODEL_NAME=gpt-5.5
OPENAI_API_KEY=your_real_openai_key
```

Replace:

- `PROJECT_REF`
- `YOUR_DB_PASSWORD`
- `REGION`
- `OPENAI_API_KEY`

If your password contains special characters like `@`, `#`, `/`, or `:`, URL-encode it before putting it in `DATABASE_URL`.

## 4. Install Dependencies

```powershell
cd C:\Users\Robiul\Downloads\Linaraman
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 5. Start The App

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open:

```text
http://127.0.0.1:8010
```

## 6. Tables

You do not need to paste SQL manually. Run:

```powershell
python scripts/init_db.py
```

The script creates the tables from `app/models.py`. The app also creates missing tables on startup.

If you want to inspect the tables in Supabase, open:

```text
Supabase Dashboard -> Table Editor
```

Expected tables include:

- `businesses`
- `users`
- `business_users`
- `whatsapp_accounts`
- `secrets`
- `customers`
- `conversations`
- `messages`
- `message_status_events`
- `knowledge_sources`
- `knowledge_chunks`
- `ai_settings`
- `tools`
- `business_tools`
- `tool_executions`
- `audit_logs`
