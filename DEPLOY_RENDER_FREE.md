# Free Render Deploy

This deploy is for staging/testing, not permanent production.

Render free web services are suitable for testing, but they can spin down when idle. Render free web service filesystems are ephemeral, so use the free Postgres database in `render.yaml` instead of SQLite.

Database tables are created automatically when the app starts.

## Steps

1. Push this project to a GitHub repository.
2. Go to Render Dashboard.
3. Create a new Blueprint from the repository.
4. Render will read `render.yaml` and create:
   - `linaraman` web service
   - `linaraman-db` Postgres database
5. The deploy is pinned to Python `3.11.11` with `.python-version` and `PYTHON_VERSION`.
6. Keep these environment values:
   - `WHATSAPP_SEND_MODE=mock`
   - `AI_MODEL_PROVIDER=mock`
7. After the first deploy, open the Render service URL.
8. Set `PUBLIC_BASE_URL` to that Render URL, for example:
   - `https://linaraman.onrender.com`
9. Set:
   - `ALLOWED_ORIGINS=https://YOUR-RENDER-SERVICE.onrender.com`
   - `ALLOWED_HOSTS=YOUR-RENDER-SERVICE.onrender.com`
10. Copy the generated `ADMIN_API_KEY` from Render environment variables. You will need it in the app's Admin key field.
11. Redeploy.

Health check:

```text
/api/platform/session
```

## Meta WhatsApp Webhook

Use:

```text
Callback URL: https://YOUR-RENDER-SERVICE.onrender.com/webhooks/meta/whatsapp
Verify token: value shown in the app WhatsApp panel
```

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
