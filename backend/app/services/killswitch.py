"""Operator kill switch, Redis-backed (OWASP ASI08, ASI10).

Two scopes, because an incident is rarely global:

- ``halt_global()`` stops every agent run in the deployment. This is the one an operator
  reaches for when something is wrong in the platform itself.
- ``halt_org(org_id)`` stops one tenant's runs, which is the common case — a runaway loop
  from a single customer's repository, or a spend incident attributable to one organisation.

**Redis, deliberately.** ARQ already requires Redis for the worker pool, so a deployment
without it cannot run jobs at all. Adding no new infrastructure dependency is worth more here
than durability of the switch state: if Redis is restarted the switches clear, and that is
the correct failure direction — an incident that has already been resolved should not leave
a tenant permanently unable to run agents.

**Reads fail open.** If Redis cannot be reached the switch reports "not halted" and logs,
rather than refusing to run. A kill switch that takes the whole platform down when its own
store is unreachable is a worse incident than the one it was built for. The failure is logged
loudly so an operator knows the switch is inoperable at that moment.
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from app.core.config import settings
from app.jobs.queue import get_arq_pool

logger = logging.getLogger("fussion.killswitch")

_GLOBAL_KEY: Final = "fussion:killswitch:global"
_ORG_PREFIX: Final = "fission:killswitch:org:"


class KillswitchUnavailable(Exception):
    """The switch could not be read or written. The kill switch is inoperable."""


def _org_key(organization_id: uuid.UUID) -> str:
    return f"{_ORG_PREFIX}{organization_id}"


async def _redis() -> object | None:
    pool = await get_arq_pool()
    return getattr(pool, "redis", None) if pool is not None else None


async def is_halted(organization_id: uuid.UUID | None) -> str | None:
    """Return the reason execution is halted, or ``None`` to proceed.

    Used as the ``halt_check`` callable the harness invokes before every tool call.
    """
    client = await _redis()
    if client is None:
        logger.error("Killswitch unavailable: no Redis pool; proceeding without a halt check.")
        return None
    try:
        if await client.get(_GLOBAL_KEY):
            return "Operator halted all agent execution."
        if organization_id is not None and await client.get(_org_key(organization_id)):
            return f"Operator halted agent execution for organization {organization_id}."
        return None
    except Exception as exc:  # noqa: BLE001 - fail open, but say so
        logger.error("Killswitch read failed; proceeding without a halt check: %s", exc)
        return None


async def halt_global() -> None:
    await _set(_GLOBAL_KEY, "Global agent execution halted by operator.")


async def resume_global() -> None:
    await _clear(_GLOBAL_KEY)


async def halt_org(organization_id: uuid.UUID) -> None:
    await _set(_org_key(organization_id), "Agent execution halted for this organization.")


async def resume_org(organization_id: uuid.UUID) -> None:
    await _clear(_org_key(organization_id))


async def status() -> dict[str, object]:
    """Current switch state, for the Studio. Reads fail closed here, unlike ``is_halted``."""
    client = await _redis()
    if client is None:
        return {"available": False, "global_halted": None, "halted_organizations": None}
    try:
        keys = [key async for key in client.scan_iter(f"{_ORG_PREFIX}*")]
        return {
            "available": True,
            "global_halted": bool(await client.get(_GLOBAL_KEY)),
            "halted_organizations": [key.removeprefix(_ORG_PREFIX) for key in keys],
            "threshold": settings.AGENT_CIRCUIT_BREAKER_THRESHOLD,
        }
    except Exception as exc:  # noqa: BLE001 - report rather than raise into a status page
        logger.error("Killswitch status read failed: %s", exc)
        return {"available": False, "error": str(exc)}


async def _set(key: str, reason: str) -> None:
    client = await _redis()
    if client is None:
        raise KillswitchUnavailable("No Redis pool; the kill switch cannot be engaged.")
    try:
        await client.set(key, reason)
    except Exception as exc:
        raise KillswitchUnavailable(f"Could not engage the kill switch: {exc}") from exc
    logger.warning("KILLSWITCH ENGAGED: %s (%s)", key, reason)


async def _clear(key: str) -> None:
    client = await _redis()
    if client is None:
        raise KillswitchUnavailable("No Redis pool; the kill switch cannot be released.")
    try:
        await client.delete(key)
    except Exception as exc:
        raise KillswitchUnavailable(f"Could not release the kill switch: {exc}") from exc
    logger.warning("KILLSWITCH RELEASED: %s", key)