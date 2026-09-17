"""Tests for Redis configuration, connection pooling, pub/sub fallback, and ARQ jobs."""

import uuid

import pytest

from app.core.config import Settings
from app.core.redis import (
    close_redis,
    project_event_channel,
    publish_audit_event,
)
from app.jobs.queue import (
    close_arq_pool,
    enqueue_analysis,
    enqueue_pipeline_execution,
)
from app.jobs.worker import WorkerSettings


def test_project_event_channel_format() -> None:
    project_id = uuid.uuid4()
    channel = project_event_channel(project_id)
    assert channel == f"fussion:events:{project_id}"


def test_effective_redis_url_resolution() -> None:
    # 1. Default unset
    s1 = Settings(REDIS_URL=None, REDIS_PRIVATE_URL=None, REDISHOST=None)
    assert s1.effective_redis_url is None

    # 2. Direct REDIS_URL
    s2 = Settings(REDIS_URL="redis://localhost:6379/0")
    assert s2.effective_redis_url == "redis://localhost:6379/0"

    # 3. Railway REDISHOST/REDISPORT/REDISPASSWORD
    s3 = Settings(
        REDIS_URL=None,
        REDISHOST="redis.railway.internal",
        REDISPORT=6379,
        REDISPASSWORD="secretpassword",
    )
    assert s3.effective_redis_url == "redis://default:secretpassword@redis.railway.internal:6379"


@pytest.mark.asyncio
async def test_publish_audit_event_without_redis_fails_safely() -> None:
    # When redis is unconfigured, publish_audit_event should return False without raising
    class MockEvent:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.project_id = uuid.uuid4()
            self.event_type = "test.event"
            self.payload = {"data": 123}

    res = await publish_audit_event(MockEvent())
    assert res is False


@pytest.mark.asyncio
async def test_publish_audit_event_without_project_id_returns_false() -> None:
    class MockEvent:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.project_id = None
            self.event_type = "org.event"

    res = await publish_audit_event(MockEvent())
    assert res is False


@pytest.mark.asyncio
async def test_close_redis_is_safe_when_unconnected() -> None:
    await close_redis()
    # Double close is safe
    await close_redis()


def test_worker_settings_declares_tasks() -> None:
    funcs = WorkerSettings.functions
    assert len(funcs) == 2
    func_names = [f.__name__ for f in funcs]
    assert "analyze_website_integration_task" in func_names
    assert "execute_integration_pipeline_task" in func_names
    assert WorkerSettings.job_timeout == 600


@pytest.mark.asyncio
async def test_enqueue_without_redis_returns_none() -> None:
    analysis_job_id = await enqueue_analysis(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    assert analysis_job_id is None

    pipeline_job_id = await enqueue_pipeline_execution(
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    )
    assert pipeline_job_id is None

    await close_arq_pool()
