"""M10F-A verified local full-instance backup and restore."""

from importlib import import_module

_backup_module = import_module("soloring.recovery.backup")

from soloring.recovery.semantic_successors import install_successor_semantics

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
