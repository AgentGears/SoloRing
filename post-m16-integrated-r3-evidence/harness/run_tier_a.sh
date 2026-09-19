#!/usr/bin/env bash
# R3 Tier-A certifying run: frozen §6.4 guard wrappers (verbatim,
# extracted from the frozen R3 spec text) + the external R3 harness
# driver. Run from the repository root in Git Bash. Per the frozen
# §6.4/§20 contract: results/ is prepared BEFORE launch; the driver
# transcript is captured contemporaneously; the true driver exit is
# captured through the pipeline; no post-run transcript
# reconstruction. No startup adapter of any kind (the guard's
# database mechanism is the supported SOLORING_* settings
# environment; TMPDIR is pinned outside the checkout as environment
# preparation).
set -uo pipefail

ROOT="$(pwd)"
CK="C:/AI/SoloRing/post-m16-r2-ck"
EV="C:/AI/SoloRing/post-m16-integrated-r3-evidence"
FREEZE="C:/AI/SoloRing/post-m16-r3-freeze"
VENV_BIN="C:/AI/SoloRing/.venv/Scripts"
PYTHONDONTWRITEBYTECODE=1
PATH="$VENV_BIN:$PATH"
TMPDIR="C:/AI/SoloRing/post-m16-integrated-r3-evidence/guard-tmp"
export PYTHONDONTWRITEBYTECODE PATH TMPDIR CK EV

mkdir -p "$EV/guards" "$EV/commands" "$EV/results" "$EV/guard-tmp"
cp "$EV/harness/guard-pre.sh" "$EV/harness/guard-post.sh" "$EV/guards/"

# oracle copies into the §20 evidence layout (byte-identical)
mkdir -p "$EV/oracles"
cp "$FREEZE"/oracles/* "$EV/oracles/"

cmd_record () {  # name command exit_code start end artifact
    cat > "$EV/commands/$1.json" <<EOF
{
 "command": "$2",
 "working_directory": "$ROOT",
 "start_utc": "$4",
 "end_utc": "$5",
 "exit_status": $3,
 "stdout_stderr_artifact": "$6"
}
EOF
}

echo "=== R3 Tier-A certifying run: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# ---------------------------------------------------------------- pre-guard
T0="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{
  echo "guard_start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "wrapper_pwd=$PWD"
  echo "CK=$CK"
  echo "EV=$EV"
  bash -x "$EV/guards/guard-pre.sh" 2>&1
  echo "guard_exit=$?"
  echo "guard_end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EV/guards/identity-guard-tier-a-pre.log" 2>&1
PRE_RC=$?
grep -q "^guard_exit=0$" "$EV/guards/identity-guard-tier-a-pre.log" || PRE_RC=2
cmd_record tier-a-pre-guard "frozen §6.4 pre-guard wrapper (verbatim)" \
  "$PRE_RC" "$T0" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "guards/identity-guard-tier-a-pre.log"
if [ "$PRE_RC" -ne 0 ]; then
  echo "PRE-GUARD FAILED (exit $PRE_RC) — run not certifying; aborting"
  exit 2
fi
echo "--- pre-guard guard_exit=0"

# ---------------------------------------------------------------- driver
T0="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$VENV_BIN/python.exe" "$EV/harness/r3_tier_a.py" \
  --ck "$CK" --ev "$EV" --freeze "$FREEZE" \
  2>&1 | tee "$EV/results/pytest-tier-a.txt"
DRV_RC=${PIPESTATUS[0]}
cmd_record tier-a-driver \
  ".venv python r3_tier_a.py --ck \$CK --ev \$EV --freeze \$FREEZE" \
  "$DRV_RC" "$T0" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "results/pytest-tier-a.txt"
echo "--- driver exit $DRV_RC"

# ---------------------------------------------------------------- post-guard
T0="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{
  echo "guard_start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "wrapper_pwd=$PWD"
  echo "CK=$CK"
  echo "EV=$EV"
  bash -x "$EV/guards/guard-post.sh" 2>&1
  echo "guard_exit=$?"
  echo "guard_end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EV/guards/identity-guard-tier-a-post.log" 2>&1
POST_RC=$?
grep -q "^guard_exit=0$" "$EV/guards/identity-guard-tier-a-post.log" || POST_RC=2
cmd_record tier-a-post-guard "frozen §6.4 post-guard wrapper (verbatim)" \
  "$POST_RC" "$T0" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "guards/identity-guard-tier-a-post.log"
if [ "$POST_RC" -ne 0 ]; then
  echo "POST-GUARD FAILED (exit $POST_RC) — run not certifying"
fi
echo "--- post-guard rc=$POST_RC"

# ---------------------------------------------------------------- package
"$VENV_BIN/python.exe" "$EV/harness/package_evidence.py" \
  --ev "$EV" --freeze "$FREEZE" --driver-rc "$DRV_RC" \
  --pre-rc "$PRE_RC" --post-rc "$POST_RC"
PKG_RC=$?
echo "=== packaging exit $PKG_RC; driver=$DRV_RC pre=$PRE_RC post=$POST_RC ==="
exit $PKG_RC
