from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from soloring.errors import SoloRingError
from soloring.spatial import error_codes as ec
from soloring.spatial.worker_inputs import (
    VerifiedDerivedInput,
    execute_schema3_derived_inputs,
)


def _verified(path: Path, data: bytes) -> VerifiedDerivedInput:
    return VerifiedDerivedInput(
        input_key="world_depth",
        position=0,
        artifact_role="spatial.world_depth",
        node="101",
        field="control_images",
        blob_hash=hashlib.sha256(data).hexdigest(),
        local_path=str(path),
    )


async def test_transport_hash_fence_rejects_changed_blob_before_upload(
    tmp_path, monkeypatch
):
    original = b"historical-derived-bytes"
    path = tmp_path / "derived.bin"
    path.write_bytes(b"changed-after-historical-verification")
    verified = _verified(path, original)

    async def _load(*args, **kwargs):
        return [verified]

    from soloring.spatial import worker_inputs as module

    monkeypatch.setattr(module, "load_verified_derived_inputs", _load)

    class NeverUploader:
        called = False

        async def upload(self, **kwargs):
            self.called = True
            raise AssertionError("corrupt bytes must fail before upload")

        async def upload_bytes(self, **kwargs):
            self.called = True
            raise AssertionError("corrupt bytes must fail before upload")

    uploader = NeverUploader()
    with pytest.raises(SoloRingError) as excinfo:
        await execute_schema3_derived_inputs(
            None,
            None,
            generation_id="11111111-1111-4111-8111-111111111111",
            attempt_id="22222222-2222-4222-8222-222222222222",
            workflow_spec={},
            manifest_v3={},
            client=uploader,
        )
    assert excinfo.value.code == ec.DERIVED_SPATIAL_BLOB_CORRUPT
    assert uploader.called is False


async def test_whole_file_transport_preserves_upload_seam_and_verified_buffer(
    tmp_path, monkeypatch
):
    original = b"historical-derived-bytes"
    path = tmp_path / "derived.bin"
    path.write_bytes(original)
    verified = _verified(path, original)

    async def _load(*args, **kwargs):
        return [verified]

    from soloring.spatial import worker_inputs as module

    monkeypatch.setattr(module, "load_verified_derived_inputs", _load)

    class UploadOnlyRecorder:
        def __init__(self) -> None:
            self.source_path: Path | None = None
            self.data: bytes | None = None

        async def upload(
            self, *, source_path: Path, filename: str, subfolder: str
        ) -> tuple[str, str]:
            # Simulate hostile replacement of the authoritative Blob path
            # after the transport fence. The uploader must read the private
            # copy made from the already-verified buffer, not this path.
            path.write_bytes(b"replacement-after-fence")
            self.source_path = source_path
            self.data = source_path.read_bytes()
            return filename, subfolder

    uploader = UploadOnlyRecorder()
    result = await execute_schema3_derived_inputs(
        None,
        None,
        generation_id="11111111-1111-4111-8111-111111111111",
        attempt_id="22222222-2222-4222-8222-222222222222",
        workflow_spec={},
        manifest_v3={},
        client=uploader,
    )

    assert uploader.source_path is not None
    assert uploader.source_path != path
    assert uploader.data == original
    assert hashlib.sha256(uploader.data).hexdigest() == verified.blob_hash
    assert result[0].execution_reference is not None


def test_projection_retains_shared_loader_until_last_spatial_consumer_removed():
    """A certified ControlNet loader may be shared by multiple stages.

    Removing one inactive stage must retain the loader while an active stage
    still consumes it; projecting the last consumer away must then remove the
    now-unreferenced loader. This closes the final-head Codex shared-loader
    review case without admitting non-spatial ownership of the loader.
    """
    from soloring.spatial import production_package as prod
    from soloring.spatial.package3 import (
        project_schema3_spatial_control_subset,
        validate_schema3_fingerprint_template,
    )

    manifest = prod.production_manifest_v3()
    template = prod.production_template()
    template["121"]["inputs"]["controlnet"] = ["110", 0]
    template.pop("120")

    # Positive control: this shared-loader graph is valid under the captured
    # fingerprint contract before projection.
    validate_schema3_fingerprint_template(
        prod.production_fingerprint_document(), template)

    partial = project_schema3_spatial_control_subset(
        manifest, template, ("world_depth", "entity_depth_1"))
    assert "121" not in partial
    assert "110" in partial
    assert partial["111"]["inputs"]["controlnet"] == ["110", 0]
    assert partial["60"]["inputs"]["model"] == ["111", 0]

    final = project_schema3_spatial_control_subset(
        manifest, template, ("world_depth",))
    assert "111" not in final
    assert "121" not in final
    assert "110" not in final
    assert final["60"]["inputs"]["model"] == ["101", 0]
