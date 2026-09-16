"""Slug generation shared by resources that use a human-readable URL key.

One implementation, so organizations and projects cannot drift apart. A slug is
lowercase, hyphen-separated, and unique within its parent.
"""

import re


def slugify(text: str, fallback: str = "item") -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return clean or fallback
