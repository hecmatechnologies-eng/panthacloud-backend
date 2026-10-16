"""Email as a channel (ADR-004).

Four modules, split so that changing email provider touches :mod:`provider` and nothing else:

- :mod:`provider` - every call to, and every signature from, the provider
- :mod:`threading` - quoted replies, which is email's own problem and no other channel's
- :mod:`inbound` - turns an arrival into the channel-neutral :class:`IncomingMessage`
- :mod:`outbound` - sends the reply
"""

from __future__ import annotations

__all__: list[str] = []