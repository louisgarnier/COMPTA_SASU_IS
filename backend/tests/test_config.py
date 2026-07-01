from backend.config import settings


def test_config_has_defaults():
    assert settings.database_url.startswith("sqlite")
    assert settings.log_level in {"DEBUG", "INFO", "WARNING", "ERROR"}
