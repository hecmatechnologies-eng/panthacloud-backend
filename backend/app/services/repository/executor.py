"""Dedicated, bounded ThreadPoolExecutor for Git commands and filesystem I/O.

Decouples heavy blocking subprocesses (git clone, rev-parse, commit) and file reading/searching
(ripgrep, directory tree walks) from Python's default asyncio thread pool.

Python's default asyncio executor has min(32, cpu_count + 4) workers (only 6 workers on a 2-vCPU
container). A dedicated, bounded pool prevents repository operations from starving other threads
in the application.
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger("fussion.repository.executor")

# Dedicated pool for disk and git subprocess operations
_MAX_IO_WORKERS = 16
_io_executor: ThreadPoolExecutor | None = None


def get_io_executor() -> ThreadPoolExecutor:
    """Retrieve or lazily initialize the dedicated I/O ThreadPoolExecutor."""
    global _io_executor
    if _io_executor is None:
        logger.info("Initializing dedicated I/O ThreadPoolExecutor with %d workers", _MAX_IO_WORKERS)
        _io_executor = ThreadPoolExecutor(
            max_workers=_MAX_IO_WORKERS,
            thread_name_prefix="fussion_io",
        )
    return _io_executor


async def run_in_io_thread[T](func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute a synchronous, blocking function on the dedicated I/O thread pool."""
    loop = asyncio.get_running_loop()
    executor = get_io_executor()
    if kwargs:
        call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, call)
    return await loop.run_in_executor(executor, func, *args)


def shutdown_io_executor(wait: bool = False) -> None:
    """Dispose of the dedicated thread pool on application shutdown."""
    global _io_executor
    if _io_executor is not None:
        logger.info("Shutting down dedicated I/O ThreadPoolExecutor")
        _io_executor.shutdown(wait=wait, cancel_futures=True)
        _io_executor = None
