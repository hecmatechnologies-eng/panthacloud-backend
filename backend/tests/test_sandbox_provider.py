"""Step C · C14 — the sandbox contract: a workspace is not a sandbox (CLAUDE.md §2, §4.6).

`LocalWorkspaceProvider` contains Fussion's own file writes; it executes nothing. The
`SandboxProvider` Protocol describes what a real backend must offer, and the workspace provider
refuses `run()` rather than pretending to satisfy it.
"""

import tempfile

import pytest

from app.services.integration.sandbox import (
    LocalWorkspaceProvider,
    SandboxNotSupportedError,
    SandboxProvider,
)


def test_local_workspace_provider_satisfies_the_sandbox_protocol_shape() -> None:
    assert isinstance(LocalWorkspaceProvider(), SandboxProvider)


def test_run_refuses_because_nothing_executes_customer_code() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        provider = LocalWorkspaceProvider(base_dir=tmpdir)
        with pytest.raises(SandboxNotSupportedError):
            provider.run(tmpdir, ["python", "-c", "print('should never run')"])
