"""Resolve the GitHub credential for an integration (step E2).

An App-linked integration stores no credential: a short-lived installation token is minted on
demand. A PAT-linked integration decrypts its stored token. Neither ever reaches the model
(`CLAUDE.md` §4.2).
"""

import logging

from app.core.secrets import SecretStoreError, secret_store
from app.models.website_integration import WebsiteIntegration
from app.services.integration.github_app import (
    GitHubAppError,
    GitHubAppNotConfiguredError,
    mint_installation_token,
)

logger = logging.getLogger("fussion.integration.credentials")


class GitHubCredentialError(Exception):
    """The GitHub credential for an integration could not be resolved."""


async def resolve_github_token(integration: WebsiteIntegration) -> str | None:
    """The token to reach the integration's repository, or None for an unauthenticated read."""
    if integration.github_installation_id is not None:
        try:
            return await mint_installation_token(integration.github_installation_id)
        except GitHubAppNotConfiguredError as exc:
            raise GitHubCredentialError(
                "The GitHub App is not configured, so this integration cannot authenticate."
            ) from exc
        except GitHubAppError as exc:
            raise GitHubCredentialError(
                "Could not obtain a GitHub installation token for this integration."
            ) from exc
    return _decrypt_pat(integration)


def _decrypt_pat(integration: WebsiteIntegration) -> str | None:
    if not integration.encrypted_secrets:
        return None
    try:
        return secret_store.decrypt(integration.encrypted_secrets).get("github_token")
    except SecretStoreError:
        # Reachable whenever the encryption key changes — e.g. development keys are generated per
        # installation, so ciphertext stored under the old hardcoded key cannot be read. The caller
        # proceeds unauthenticated, which fails confusingly, so say why here.
        logger.warning(
            "Stored credentials for integration %s could not be decrypted with the current "
            "SECRET_ENCRYPTION_KEY; the token must be re-entered.",
            integration.id,
        )
        return None
