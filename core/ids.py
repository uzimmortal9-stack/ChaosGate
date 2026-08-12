from __future__ import annotations

import uuid


def nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
