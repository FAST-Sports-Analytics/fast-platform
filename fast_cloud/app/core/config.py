from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FAST Cloud"
    environment: str = "development"
    database_url: str = "sqlite:///./fast_cloud.db"
    database_pool_pre_ping: bool = True
    database_pool_recycle_seconds: int = 1800
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8766
    release_storage_path: str = "./releases/packages"
    backup_storage_path: str = "./backups"
    bootstrap_admin: bool = False
    rotate_admin_password: bool = False
    jwt_secret: str = "development-only-change-me"
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    admin_portal_session_days: int = 7
    admin_email: str = "admin@fastsportsanalytics.com"
    admin_password: str = "ChangeMe123!"
    public_app_url: str = "https://www.fastsportsanalytics.com"
    invite_expiry_hours: int = 72
    password_reset_expiry_minutes: int = 60
    password_reset_rate_attempts: int = 5
    password_reset_rate_window_seconds: int = 900
    token_submit_rate_attempts: int = 10
    token_submit_rate_window_seconds: int = 900
    invitation_resend_rate_attempts: int = 5
    invitation_resend_rate_window_seconds: int = 3600
    email_provider: str = "auto"
    email_from_name: str = "FAST Sports Analytics"
    email_from_email: str = ""
    email_reply_to: str = "support@fastsportsanalytics.com"
    email_timeout_seconds: int = 15
    resend_api_key: str = ""
    resend_api_base: str = "https://api.resend.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "no-reply@fastsportsanalytics.com"  # legacy L9 compatibility
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    # Stripe Billing (optional until commercial launch)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    billing_currency: str = "gbp"
    billing_grace_days: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FAST_CLOUD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
