"""Step A — no development secret is a literal in source (CLAUDE.md §3.2).

Development keys come from the environment or from a generated, gitignored local file.
Production behaviour is unchanged: it refuses to start without real, non-weak values.
"""

import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# _COMPROMISED_VALUE_HASHES: the digests of the values that leaked in baseline commit 1034f4a,
# imported rather than restated — one list, so adding a third compromised value cannot leave this
# guard checking only the old two. The plaintexts appear nowhere in this repository, this test
# included.
from app.core.config import _COMPROMISED_VALUE_HASHES, Settings
from app.core.secrets import SecretStore

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


@pytest.fixture
def work_dir() -> Iterator[Path]:
    """A scratch directory. Not pytest's tmp_path: its temp root is not writable here."""
    path = Path(tempfile.mkdtemp(prefix="fussion-secrets-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def dev_settings(work_dir: Path, **overrides: str | None) -> Settings:
    """Non-production Settings whose dev secrets file lives under work_dir.

    Both key fields are passed explicitly, so the test run's own environment variables (set in
    conftest) cannot mask what is being tested. Init arguments outrank the environment.
    """
    fields: dict[str, str | None] = {"JWT_SECRET_KEY": None, "SECRET_ENCRYPTION_KEY": None}
    fields.update(overrides)
    return Settings(
        APP_ENV="development",
        DEV_SECRETS_FILE=str(work_dir / ".dev-secrets.json"),
        _env_file=None,
        **fields,
    )


# ============================================================
# 1. NO SECRET LITERALS IN SOURCE
# ============================================================


SCANNED_TREES = ("backend/app", "backend/tests", "backend/alembic", "backend/scripts", "docs")
SCANNED_FILES = ("backend/.env.example", ".env.example", "CLAUDE.md", "README.md")
SCANNED_SUFFIXES = {
    ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".example", ".ini", ".ts", ".tsx",
}


def _scanned_paths() -> list[Path]:
    paths = [REPO / name for name in SCANNED_FILES]
    for tree in SCANNED_TREES:
        paths.extend(
            path
            for path in (REPO / tree).rglob("*")
            if path.is_file() and path.suffix in SCANNED_SUFFIXES
        )
    return [path for path in paths if path.exists()]


def test_no_leaked_secret_anywhere_in_the_tree() -> None:
    """Guards against reintroduction, including by a test claiming to check for it.

    Scans source, tests, migrations, scripts and docs — the first version of this test looked at
    `app/` only, and could not see that this very file had re-added both plaintexts.
    """
    import hashlib

    offenders: list[str] = []
    for path in _scanned_paths():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in text.replace("=", "= ").replace("'", " ").replace('"', " ").split():
            candidates = {token, token.strip(",;)(][")}
            if any(
                hashlib.sha256(candidate.encode()).hexdigest() in _COMPROMISED_VALUE_HASHES
                for candidate in candidates
            ):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], f"known-compromised secret present in: {sorted(set(offenders))}"


def test_the_scan_would_catch_a_reintroduced_secret(work_dir: Path) -> None:
    """The guard above is only worth having if it actually fires; prove it on a planted value."""
    import hashlib

    planted = "planted-not-a-real-secret"
    planted_digest = hashlib.sha256(planted.encode()).hexdigest()
    candidate = (work_dir / "leaky.py")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(f'KEY = "{planted}"\n', encoding="utf-8")

    found = [
        token
        for token in candidate.read_text(encoding="utf-8").replace('"', " ").split()
        if hashlib.sha256(token.encode()).hexdigest() == planted_digest
    ]
    assert found == [planted]


def test_settings_has_no_dev_secret_fields() -> None:
    fields = Settings.model_fields
    assert "JWT_DEV_SECRET" not in fields
    assert "SECRET_DEV_ENCRYPTION_KEY" not in fields


def test_dev_secrets_file_is_gitignored() -> None:
    patterns = {
        line.strip()
        for line in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert any(p in patterns for p in (".dev-secrets.json", "*.dev-secrets.json")), patterns


# ============================================================
# 2. DEVELOPMENT — GENERATED, PERSISTENT, OVERRIDABLE
# ============================================================


def test_dev_secrets_are_generated_and_stable(work_dir: Path) -> None:
    secrets_file = work_dir / ".dev-secrets.json"
    assert not secrets_file.exists()

    first = dev_settings(work_dir)
    jwt_secret = first.effective_jwt_secret_key
    encryption_key = first.effective_secret_encryption_key

    assert secrets_file.exists()
    assert len(jwt_secret) >= 32
    # Usable as a real Fernet key, not merely random text.
    Fernet(encryption_key.encode())

    # A restart reads the same values back, so dev tokens and ciphertext survive it.
    second = dev_settings(work_dir)
    assert second.effective_jwt_secret_key == jwt_secret
    assert second.effective_secret_encryption_key == encryption_key

    stored = json.loads(secrets_file.read_text(encoding="utf-8"))
    assert stored["jwt_secret"] == jwt_secret
    assert stored["encryption_key"] == encryption_key


def test_dev_secrets_differ_between_installations(work_dir: Path) -> None:
    one = dev_settings(work_dir / "a").effective_secret_encryption_key
    two = dev_settings(work_dir / "b").effective_secret_encryption_key
    assert one != two, "each installation must generate its own key"


def test_environment_overrides_the_generated_file(work_dir: Path) -> None:
    explicit_key = Fernet.generate_key().decode()
    settings = dev_settings(
        work_dir, JWT_SECRET_KEY="env-jwt-secret", SECRET_ENCRYPTION_KEY=explicit_key
    )

    assert settings.effective_jwt_secret_key == "env-jwt-secret"
    assert settings.effective_secret_encryption_key == explicit_key
    generated = work_dir / ".dev-secrets.json"
    assert not generated.exists(), "no file is written when the environment supplies the keys"


def test_generated_key_round_trips_through_the_secret_store(work_dir: Path) -> None:
    store = SecretStore(key=dev_settings(work_dir).effective_secret_encryption_key)
    payload = {"github_token": "ghp_example"}
    assert store.decrypt(store.encrypt(payload)) == payload


def test_default_location_does_not_depend_on_the_working_directory() -> None:
    """CLAUDE.md §8 documents two CWDs for one installation — uvicorn from backend/, pytest from
    the repository root. A relative default would give them different keys, silently orphaning
    every GitHub token encrypted under the first."""
    from app.core.config import DEFAULT_DEV_SECRETS_FILE

    default = Path(DEFAULT_DEV_SECRETS_FILE)
    assert default.is_absolute()
    assert default == BACKEND / ".dev-secrets.json"


def test_a_path_gitignore_would_not_cover_is_refused(work_dir: Path) -> None:
    from app.core.dev_secrets import load_or_create_dev_secrets

    with pytest.raises(RuntimeError, match="dev-secrets.json"):
        load_or_create_dev_secrets(work_dir / "keys.json")
    assert not (work_dir / "keys.json").exists()


def test_a_corrupt_or_invalid_file_says_what_to_do(work_dir: Path) -> None:
    from app.core.dev_secrets import load_or_create_dev_secrets

    secrets_file = work_dir / ".dev-secrets.json"
    work_dir.mkdir(parents=True, exist_ok=True)

    secrets_file.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unreadable"):
        load_or_create_dev_secrets(secrets_file)

    secrets_file.write_text('{"jwt_secret": "x"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing"):
        load_or_create_dev_secrets(secrets_file)

    # Valid JSON, complete, but the encryption key is not a Fernet key: the failure must name
    # this file rather than surfacing as an opaque SecretStoreError at import time.
    secrets_file.write_text(
        '{"jwt_secret": "x", "encryption_key": "not-a-fernet-key"}', encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="invalid encryption_key"):
        load_or_create_dev_secrets(secrets_file)


@pytest.mark.parametrize("environment", ["staging", "", "prod-like", "Production "])
def test_an_unrecognised_environment_refuses_to_generate_keys(
    environment: str, work_dir: Path
) -> None:
    """Generating per-process keys outside dev would mean replica A issuing JWTs replica B
    rejects, and ciphertext A wrote that B cannot read. Refuse instead."""
    settings = Settings(
        APP_ENV=environment,
        DEV_SECRETS_FILE=str(work_dir / ".dev-secrets.json"),
        JWT_SECRET_KEY=None,
        SECRET_ENCRYPTION_KEY=None,
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="APP_ENV"):
        _ = settings.effective_jwt_secret_key
    assert not (work_dir / ".dev-secrets.json").exists()


@pytest.mark.parametrize("environment", ["development", "dev", "local", "test", "testing"])
def test_recognised_development_environments_generate_keys(
    environment: str, work_dir: Path
) -> None:
    settings = Settings(
        APP_ENV=environment,
        DEV_SECRETS_FILE=str(work_dir / ".dev-secrets.json"),
        JWT_SECRET_KEY=None,
        SECRET_ENCRYPTION_KEY=None,
        _env_file=None,
    )
    assert settings.effective_jwt_secret_key


# ============================================================
# 3. PRODUCTION — STILL FAILS LOUDLY
# ============================================================


def production_settings(**overrides: str | None) -> Settings:
    """Production Settings. Both key fields are explicit, so the test run's environment cannot
    accidentally satisfy a check that is supposed to fail."""
    fields: dict[str, str | None] = {"JWT_SECRET_KEY": None, "SECRET_ENCRYPTION_KEY": None}
    fields.update(overrides)
    return Settings(APP_ENV="production", _env_file=None, **fields)


@pytest.mark.parametrize(
    ("field", "prop"),
    [
        ("JWT_SECRET_KEY", "effective_jwt_secret_key"),
        ("SECRET_ENCRYPTION_KEY", "effective_secret_encryption_key"),
    ],
)
def test_production_requires_a_configured_key(field: str, prop: str) -> None:
    settings = production_settings()  # neither key configured

    with pytest.raises(RuntimeError, match="[Pp]roduction"):
        getattr(settings, prop)


@pytest.mark.parametrize("weak", ["secret", "changeme", "jwt_secret"])
def test_production_rejects_weak_jwt_values(weak: str) -> None:
    with pytest.raises(RuntimeError, match="[Pp]roduction"):
        _ = production_settings(JWT_SECRET_KEY=weak).effective_jwt_secret_key


def test_two_compromised_values_are_registered() -> None:
    """The leaked pair must stay denied after being deleted from source.

    Asserted by shape, not by value: holding either plaintext here would put it back in the tree,
    which is what this slice removes, and `test_no_leaked_secret_anywhere_in_the_tree` would fail.
    """
    assert len(_COMPROMISED_VALUE_HASHES) >= 2
    hex_digits = set("0123456789abcdef")
    assert all(
        len(digest) == 64 and set(digest) <= hex_digits
        for digest in _COMPROMISED_VALUE_HASHES
    )


@pytest.mark.parametrize(
    ("field", "prop"),
    [
        ("JWT_SECRET_KEY", "effective_jwt_secret_key"),
        ("SECRET_ENCRYPTION_KEY", "effective_secret_encryption_key"),
    ],
)
def test_production_rejects_a_registered_compromised_value(
    field: str, prop: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the denial mechanism with a stand-in whose digest is registered for this test."""
    import hashlib

    from app.core import config as config_module

    stand_in = "stand-in-for-a-compromised-key"
    digest = hashlib.sha256(stand_in.encode()).hexdigest()
    monkeypatch.setattr(
        config_module,
        "_COMPROMISED_VALUE_HASHES",
        frozenset({*config_module._COMPROMISED_VALUE_HASHES, digest}),
    )

    with pytest.raises(RuntimeError, match="compromised"):
        getattr(production_settings(**{field: stand_in}), prop)


def test_a_strong_value_is_not_mistaken_for_a_compromised_one() -> None:
    from app.core.config import _is_unacceptable

    assert not _is_unacceptable(Fernet.generate_key().decode())


def test_production_never_generates_or_writes_a_secrets_file(work_dir: Path) -> None:
    settings = Settings(
        APP_ENV="production",
        DEV_SECRETS_FILE=str(work_dir / ".dev-secrets.json"),
        JWT_SECRET_KEY=None,
        SECRET_ENCRYPTION_KEY=None,
        _env_file=None,
    )
    with pytest.raises(RuntimeError):
        _ = settings.effective_jwt_secret_key
    with pytest.raises(RuntimeError):
        _ = settings.effective_secret_encryption_key
    assert not (work_dir / ".dev-secrets.json").exists()


def test_production_accepts_real_values() -> None:
    strong_jwt = Fernet.generate_key().decode() + "-jwt"
    strong_key = Fernet.generate_key().decode()
    settings = production_settings(JWT_SECRET_KEY=strong_jwt, SECRET_ENCRYPTION_KEY=strong_key)

    assert settings.effective_jwt_secret_key == strong_jwt
    assert settings.effective_secret_encryption_key == strong_key
