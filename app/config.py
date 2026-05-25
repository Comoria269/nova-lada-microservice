"""
Configuration centralisée.
Charge les variables d'environnement et valide leur présence au boot.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Stripe
    stripe_api_key: str
    stripe_webhook_secret: str

    # Brevo
    brevo_api_key: str
    brevo_template_confirmation_id: int = 2
    brevo_template_expedition_id: int = 3
    brevo_template_avis_id: int = 4

    # Admin
    admin_api_token: str

    # Redis (idempotence webhooks)
    redis_url: str

    # Misc
    environment: str = "production"
    log_level: str = "INFO"
    default_shipping_days: int = 4


settings = Settings()  # lève une exception au boot si une variable manque
