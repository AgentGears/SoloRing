"""M10F-A local storage recovery (R5 §7).

Operational backup/restore for the default file-backed SoloRing layout.
Recovery is verify-only with respect to source history and never creates
production authority: no API route, no database table, no durable error
code. Failures are operator/recovery-tool level exceptions.
"""

from soloring.recovery.backup import (
    BackupManifestInvalid,
    RecoveryCorruption,
    RecoveryError,
    RecoveryUnsupported,
    restore,
    verify_supported_posture,
    backup,
)

__all__ = [
    "backup",
    "restore",
    "verify_supported_posture",
    "RecoveryError",
    "RecoveryUnsupported",
    "RecoveryCorruption",
    "BackupManifestInvalid",
]
