import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI WhatsApp SaaS")
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    direct_url: str = os.getenv("DIRECT_URL", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    next_public_supabase_url: str = os.getenv("NEXT_PUBLIC_SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
    next_public_supabase_publishable_key: str = os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "")
    app_secret: str = os.getenv("APP_SECRET", "dev-only-change-me")
    auth_mode: str = os.getenv("AUTH_MODE", "dev_header")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    platform_admin_emails: str = os.getenv("PLATFORM_ADMIN_EMAILS", "owner@example.com")
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000")
    allowed_hosts: str = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost")
    enable_docs: bool = os.getenv("ENABLE_DOCS", "true").lower() in {"1", "true", "yes", "on"}
    meta_app_secret: str = os.getenv("META_APP_SECRET", "")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")
    webhook_verify_token: str = os.getenv("WEBHOOK_VERIFY_TOKEN", "platform-dev-token")
    whatsapp_send_mode: str = os.getenv("WHATSAPP_SEND_MODE", "mock")
    whatsapp_graph_api_url: str = os.getenv("WHATSAPP_GRAPH_API_URL", "https://graph.facebook.com/v20.0")
    ai_model_provider: str = os.getenv("AI_MODEL_PROVIDER", "mock")
    ai_model_name: str = os.getenv("AI_MODEL_NAME", "local-mock")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    @property
    def platform_admin_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.platform_admin_emails.split(",") if email.strip()}

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def allowed_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        if self.public_base_url and self.public_base_url not in origins:
            origins.append(self.public_base_url.rstrip("/"))
        return origins

    @property
    def allowed_host_list(self) -> list[str]:
        hosts = [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]
        if self.public_base_url:
            public_host = urlsplit(self.public_base_url).netloc
            if public_host and public_host not in hosts:
                hosts.append(public_host)
        return hosts

    def validate_for_runtime(self) -> None:
        if not self.is_production:
            return
        problems: list[str] = []
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must use Postgres or another production database, not SQLite.")
        if self.app_secret in {"", "dev-only-change-me", "replace-me-with-a-long-random-secret"} or len(self.app_secret) < 32:
            problems.append("APP_SECRET must be set to a strong random value of at least 32 characters.")
        if self.webhook_verify_token in {"", "platform-dev-token"}:
            problems.append("WEBHOOK_VERIFY_TOKEN must be set to a private random value.")
        if not self.public_base_url.startswith("https://"):
            problems.append("PUBLIC_BASE_URL must be an HTTPS public URL.")
        if self.auth_mode != "admin_key":
            problems.append("AUTH_MODE must be admin_key in production.")
        if len(self.admin_api_key) < 24:
            problems.append("ADMIN_API_KEY must be set to a strong random value.")
        if "*" in self.allowed_origin_list:
            problems.append("ALLOWED_ORIGINS cannot contain * in production.")
        if "*" in self.allowed_host_list:
            problems.append("ALLOWED_HOSTS cannot contain * in production.")
        if self.whatsapp_send_mode.lower() == "live" and not self.meta_app_secret:
            problems.append("META_APP_SECRET is required when WHATSAPP_SEND_MODE=live.")
        if self.ai_model_provider == "openai" and not self.openai_api_key:
            problems.append("OPENAI_API_KEY is required when AI_MODEL_PROVIDER=openai.")
        if problems:
            raise RuntimeError("Production configuration is unsafe:\n- " + "\n- ".join(problems))


settings = Settings()
