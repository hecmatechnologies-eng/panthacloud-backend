import pytest
from app.core.config import Settings
from app.skills.loader import SkillLoader


def test_database_url_normalization_for_railway():
    # Standard Railway Postgres connection string
    s1 = Settings(DATABASE_URL="postgresql://user:pass@host:5432/db", APP_ENV="production")
    assert s1.effective_database_url == "postgresql+psycopg://user:pass@host:5432/db"

    # Legacy postgres:// scheme
    s2 = Settings(DATABASE_URL="postgres://user:pass@host:5432/db", APP_ENV="production")
    assert s2.effective_database_url == "postgresql+psycopg://user:pass@host:5432/db"

    # Already normalized scheme
    s3 = Settings(DATABASE_URL="postgresql+psycopg://user:pass@host:5432/db", APP_ENV="production")
    assert s3.effective_database_url == "postgresql+psycopg://user:pass@host:5432/db"


def test_railway_public_domain_fallback():
    # Auto-detected Railway domain
    s = Settings(
        APP_ENV="production",
        RAILWAY_PUBLIC_DOMAIN="my-backend.up.railway.app",
    )
    assert s.widget_script_url == "https://my-backend.up.railway.app/api/v1/public/widget.js"


def test_skills_loader_indexes_skills():
    loader = SkillLoader()
    skill_ids = [s.id for s in loader.index()]
    assert "generic-html" in skill_ids
    assert "nextjs-app-router" in skill_ids
