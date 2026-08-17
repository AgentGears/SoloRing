"""Cross-slice integration test (plan §48 M1C fixture rule):

upload Asset -> attach as ShotReference -> capture ShotRevision -> verify
Asset ID + Blob hash appear in the canonical snapshot.
"""

from __future__ import annotations

from soloring.api.schemas.references import ReferenceInput
from soloring.domain import references, revisions
from tests.conftest import create_project, create_shot

PNG = b"\x89PNG\r\n\x1a\n" + b"reference-image-bytes"


async def test_upload_reference_revision_snapshot_integration(
    client, factory
) -> None:
    # 1. upload a reference Asset through the HTTP pipeline
    p = await create_project(client, name="P")
    up = (
        await client.post(
            f"/projects/{p['id']}/assets",
            files={"file": ("ref.png", PNG, "image/png")},
        )
    ).json()
    asset_id, blob_hash = up["id"], up["blob_hash"]

    # 2. attach it as a ShotReference
    s = await create_shot(client, p["id"], subject="Eva enters")
    put = await client.put(
        f"/shots/{s['id']}/references",
        json={"references": [{"asset_id": asset_id, "role": "reference"}]},
    )
    assert put.status_code == 200

    # 3. capture a ShotRevision
    async with factory() as session:
        rev = await revisions.capture_revision(session, s["id"])

    # 4. the canonical snapshot carries BOTH the Asset and Blob identity
    assert asset_id in rev.snapshot_json
    assert blob_hash in rev.snapshot_json

    # and the reference round-trips through the service unchanged
    async with factory() as session:
        rows = await references.replace_references(
            session, s["id"], [ReferenceInput(asset_id=asset_id, role="reference")]
        )
    assert rows[0].asset_id == asset_id
    assert rows[0].position == 0
