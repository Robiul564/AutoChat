# Free Render Deploy

This deploy is for staging/testing, not permanent production.

Render free web services are suitable for testing, but they can spin down when idle. Render free web service filesystems are ephemeral, so use the free Postgres database in `render.yaml` instead of SQLite.

Database tables are created automatically when the app starts.

## Steps

1. Push this project to a GitHub repository.
2. Go to Render Dashboard.
3. Create a new Blueprint from the repository.
4. Render will read `render.yaml` and create:
   - `autochat` web service
   - `linaraman-db` Postgres database
5. The deploy is pinned to Python `3.11.11` with `.python-version` and `PYTHON_VERSION`.
6. Use `AI_MODEL_PROVIDER=auto` and `WHATSAPP_SEND_MODE=auto`. Add `OPENAI_API_KEY` when you want the bot to generate replies with OpenAI; without it, the app falls back to saved knowledge.
7. After the first deploy, open the Render service URL.
8. The Blueprint defaults to:
   - `PUBLIC_BASE_URL=https://autochat.onrender.com`
   - `ALLOWED_ORIGINS=https://autochat.onrender.com`
   - `ALLOWED_HOSTS=autochat.onrender.com,linaraman.onrender.com,*.onrender.com`
9. If Render creates a different service URL, update those three values to match it.
10. Copy the generated `ADMIN_API_KEY` from Render environment variables. You will need it in the app's Admin key field.
11. Redeploy.

Health check:

```text
/api/health
```

## Meta WhatsApp Webhook

Use:

```text
Callback URL: use the business-specific URL shown in the app WhatsApp panel,
for example https://YOUR-RENDER-SERVICE.onrender.com/webhooks/meta/whatsapp/business/1
Verify token: the matching value shown in the same app WhatsApp panel
```

The platform URL `/webhooks/meta/whatsapp` also works, but only when the saved
WhatsApp `phone_number_id` or WABA ID exactly matches the metadata Meta sends in
the webhook. For first setup, the business-specific URL is easier to verify.

For live WhatsApp sending, only after testing webhooks:

```env
WHATSAPP_SEND_MODE=live
META_APP_SECRET=your_meta_app_secret
```

## Production Check

Before going live, set production environment variables and run:

```powershell
python scripts/production_check.py
```

The app refuses to start in `APP_ENV=production` if critical settings are unsafe.

## Free Tier Notes

- Free Render web services can sleep when idle.
- Free Render Postgres expires after 30 days.
- SQLite data should not be used on Render free services because local files can be lost.

