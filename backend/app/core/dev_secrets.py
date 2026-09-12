"""Development-only secret provisioning.

No development secret is a literal in this repository (CLAUDE.md §3.2): the baseline commit put
the real dev encryption key into git history, and a default in source is a default that ships.

In development and test, keys come from the environment if set, and otherwise from a generated,
gitignored file — one per installation, so no two machines share a key and nothing worth leaking
lives in source. Production never reaches this module: it requires explicitly configured values
and fails loudly without them.
"""

import json
import logging
import os
from pathlib import Path
from secrets import token_urlsafe

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("fussion.dev_secrets")

JWT_SECRET_FIELD = "jwt_secret"
ENCRYPTION_KEY_FIELD = "encryption_key"
_FIELDS = (JWT_SECRET_FIELD, ENCRYPTION_KEY_FIELD)

# The filename the repository's .gitignore covers. Enforced, so pointing DEV_SECRETS_FILE at
# "keys.json" cannot produce a committable secret.
REQUIRED_SUFFIX = ".dev-secrets.json"


def load_or_create_dev_secrets(path: str | Path) -> dict[str, str]:
    """Return this installation's development secrets, generating the file on first use.

    Deliberately not cached: the caller is a settings property, and a test or a developer may
    point at a different file. A read is cheap and happens once per token operation.
    """
    secrets_file = Path(path).resolve()
    if not secrets_file.name.endswith(REQUIRED_SUFFIX):
        raise RuntimeError(
            f"DEV_SECRETS_FILE must end with {REQUIRED_SUFFIX} (got {secrets_file.name}): only "
            "that name is covered by .gitignore, and a generated key must not be committable."
        )
    if secrets_file.exists():
        return _read(secrets_file)

    generated = {
        JWT_SECRET_FIELD: token_urlsafe(48),
        ENCRYPTION_KEY_FIELD: Fernet.generate_key().decode("ascii"),
    }
    secrets_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive create, owner-only from the moment it exists: chmod after writing would leave
        # a window where the key is world-readable. If another process got there first, adopt its
        # file rather than overwrite it, which would invalidate every token and ciphertext it
        # had issued.
        #
        # On Windows — the development platform here — file modes do not map to ACLs, so this is
        # a POSIX protection only. Treat the file as readable by anything running as this user.
        def _private(file: str, flags: int) -> int:
            return os.open(file, flags, 0o600)

        with open(secrets_file, "x", encoding="utf-8", opener=_private) as handle:
            json.dump(generated, handle, indent=2)
    except FileExistsError:
        return _read(secrets_file)

    logger.warning(
        "Generated local development secrets in %s. The file is gitignored and is not a production "
        "credential. Delete it to rotate, which invalidates existing dev tokens and makes stored "
        "dev ciphertext undecryptable.",
        secrets_file,
    )
    return generated


def _read(secrets_file: Path) -> dict[str, str]:
    advice = (
        f"Delete {secrets_file} to regenerate it; existing development tokens and stored "
        "development ciphertext then become invalid."
    )
    try:
        data = json.loads(secrets_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Development secrets file is unreadable: {exc}. {advice}") from exc

    if not isinstance(data, dict) or not all(
        isinstance(data.get(field), str) and data[field] for field in _FIELDS
    ):
        raise RuntimeError(
            f"Development secrets file {secrets_file} is missing {' or '.join(_FIELDS)}. {advice}"
        )
    try:
        # Checked here so a hand-edited file fails with this advice, rather than as an opaque
        # SecretStoreError at import time that never mentions this file.
        Fernet(data[ENCRYPTION_KEY_FIELD].encode("ascii"))
    except (ValueError, TypeError, InvalidToken) as exc:
        raise RuntimeError(
            f"Development secrets file {secrets_file} has an invalid "
            f"{ENCRYPTION_KEY_FIELD} ({exc}). {advice}"
        ) from exc
    return {field: data[field] for field in _FIELDS}
