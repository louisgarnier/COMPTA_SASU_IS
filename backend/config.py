"""Central configuration loaded from environment / .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/lgc.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    enable_banking_app_id: str = os.getenv("ENABLE_BANKING_APP_ID", "")
    enable_banking_private_key_path: str = os.getenv(
        "ENABLE_BANKING_PRIVATE_KEY_PATH", "./secrets/eb_private.pem"
    )
    enable_banking_redirect_url: str = os.getenv(
        "ENABLE_BANKING_REDIRECT_URL", "http://localhost:3000/banking/callback"
    )


settings = Settings()
