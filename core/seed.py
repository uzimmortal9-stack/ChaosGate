from __future__ import annotations

import json

from core.ids import nid
from core.models import Repository, Workspace
from core.settings import DEFAULT_POLICY, SAMPLES_DIR


SAMPLES = [
    {
        "owner": "atlas-shop",
        "name": "atlas-api",
        "language": "Python",
        "description": "Catalog + checkout API. Healthy sample used to prove a green gate.",
        "folder": "atlas-api",
        "last_status": "idle",
    },
    {
        "owner": "nova-labs",
        "name": "nova-web",
        "language": "JavaScript",
        "description": "Storefront build. Passes tests; lockfile warning expected.",
        "folder": "nova-web",
        "last_status": "idle",
    },
    {
        "owner": "mercury-pay",
        "name": "checkout-service",
        "language": "Python",
        "description": "Broken checkout. Failing tests and a committed secret — should be blocked.",
        "folder": "checkout-service",
        "last_status": "idle",
    },
]


def ensure_workspace(session) -> Workspace:
    ws = session.get(Workspace, 1)
    if ws is None:
        ws = Workspace(id=1, mode="demo", policy_json=json.dumps(DEFAULT_POLICY))
        session.add(ws)
        session.commit()
    if not ws.policy_json:
        ws.policy_json = json.dumps(DEFAULT_POLICY)
        session.commit()
    return ws


def seed_samples(session) -> None:
    ws = ensure_workspace(session)
    existing = {r.full_name for r in session.query(Repository).filter_by(workspace_id=ws.id).all()}
    for spec in SAMPLES:
        full = f"{spec['owner']}/{spec['name']}"
        if full in existing:
            continue
        folder = SAMPLES_DIR / spec["folder"]
        session.add(
            Repository(
                id=nid("repo"),
                workspace_id=ws.id,
                owner=spec["owner"],
                name=spec["name"],
                full_name=full,
                html_url=None,
                default_branch="main",
                language=spec["language"],
                description=spec["description"],
                local_path=str(folder),
                is_sample=True,
                last_status=spec["last_status"],
            )
        )
    session.commit()
