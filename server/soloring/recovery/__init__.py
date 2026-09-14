"""M10F-A verified local full-instance backup and restore."""

from importlib import import_module

_backup_module = import_module("soloring.recovery.backup")

# M15 advanced the recovery head but the predecessor file kept the value as
# an inline literal.  M16-P0 gives that already-published head an explicit
# name so semantic head dispatch cannot confuse 0015 (M14) with 0016 (M15).
if not hasattr(_backup_module, "M15_ALEMBIC_HEAD"):
    _backup_module.M15_ALEMBIC_HEAD = "0016_m15_revision_compatibility"

from soloring.recovery.m16_p0_semantics import install_successor_semantics

# M16-P0 predecessor repair: M14/M15 added durable historical semantics after
# the original M10F recovery engine.  Extend the existing staged-liveness seam
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
