"""UUID helpers (plan §12, §44)."""

from __future__ import annotations

import re
import uuid

# Lowercase canonical UUID form (plan §12).
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def is_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def new_uuid() -> str:
    return str(uuid.uuid4())
