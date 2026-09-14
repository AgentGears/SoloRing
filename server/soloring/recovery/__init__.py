"""M10F-A verified local full-instance backup and restore."""

from importlib import import_module

from soloring.domain.canonical import canonical_json_str as _canonical_json_str

_backup_module = import_module("soloring.recovery.backup")

# M15 advanced the recovery head but the predecessor file kept the value as
# an inline literal. M16-P0 gives that already-published head an explicit name
# so semantic head dispatch cannot confuse 0015 (M14) with 0016 (M15).
if not hasattr(_backup_module, "M15_ALEMBIC_HEAD"):
    _backup_module.M15_ALEMBIC_HEAD = "0016_m15_revision_compatibility"

# M15 published two deterministic projections for update operations:
# operation_json uses assessment.assessment_report_hash, while operation_hash
# is derived by compatibility.canonical.operation_root, whose corresponding
# member is assessment.report_hash. Recovery must preserve that published
# history exactly rather than retroactively declaring it corrupt.
_semantic = import_module("soloring.recovery.semantic_successors")
_successor = import_module("soloring.recovery.successor_semantics")


def _published_m15_operation_json(value) -> str:
    """Render the published audit JSON when given the normalized hash root.

    The shape test is exact; every other canonical JSON check keeps the normal
    serializer unchanged. The operation hash is still independently re-derived
    from operation_root by the verifier.
    """
    if (
        isinstance(value, dict)
        and set(value) == {"assessment", "items"}
        and isinstance(value.get("assessment"), dict)
        and set(value["assessment"]) == {"assessment_id", "report_hash"}
        and isinstance(value.get("items"), list)
    ):
        value = {
            "assessment": {
                "assessment_id": value["assessment"]["assessment_id"],
                "assessment_report_hash": value["assessment"]["report_hash"],
            },
            "items": value["items"],
        }
    return _canonical_json_str(value)


_semantic.canonical_json_str = _published_m15_operation_json
_successor.verify_m15_compatibility_state = _semantic.verify_m15_compatibility_state
install_successor_semantics = _successor.install_successor_semantics

# M16-P0 predecessor repair: M14/M15 added durable historical semantics after
# the original M10F recovery engine. Extend the existing staged-liveness seam
# so backup and restore certify those successor rows before publication.
install_successor_semantics(_backup_module)

BackupManifestInvalid = _backup_module.BackupManifestInvalid
RecoveryCorruption = _backup_module.RecoveryCorruption
RecoveryError = _backup_module.RecoveryError
RecoveryUnsupported = _backup_module.RecoveryUnsupported
backup = _backup_module.backup
restore = _backup_module.restore
verify_supported_posture = _backup_module.verify_supported_posture

__all__ = [
    "backup",
    "restore",
    "verify_supported_posture",
    "RecoveryError",
    "RecoveryUnsupported",
    "RecoveryCorruption",
    "BackupManifestInvalid",
]
