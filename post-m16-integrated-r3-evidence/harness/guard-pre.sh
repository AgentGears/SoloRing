
set -e
# identity
CERTIFYING_COMMIT=8199e46da6b8592f606725059601b402ab2874b0
CERTIFYING_TREE=941d14cda84d0186431a80c0f9cbdc3fa978296b
PARENT_COMMIT=488031a2b7d0070d23425bbe04b86d9f9f16e0bd
# identity: the R3 certifying baseline (§0.2, identical commits to R2's), bound by frozen
# constants — NOT phrases about any "published" commit
test "$(git -C "$CK" rev-parse HEAD)" = "$CERTIFYING_COMMIT"
test "$(git -C "$CK" rev-parse 'HEAD^{tree}')" = "$CERTIFYING_TREE"
test "$(git -C "$CK" rev-parse HEAD^)" = "$PARENT_COMMIT"
test "$(git -C "$CK" diff --name-only HEAD^..HEAD | sort | tr '\n' ' ')" \
  = "server/soloring/recovery/backup.py tests/test_m15_recovery.py "
# clean checkout
test -z "$(git -C "$CK" status --porcelain --untracked-files=no)"
# untracked non-ignored files are ALSO forbidden (ignored entries like
# __pycache__/ remain excluded by git ignore rules)
test -z "$(git -C "$CK" status --porcelain)"
test -z "$(git -C "$CK" diff-index --cached HEAD)"
# migration baseline: terminal revision is exactly 0017, none later
test "$(ls "$CK/server/alembic/versions" | grep -c '^0017_m16_intra_shot_consequences.py$')" = 1
test "$(ls "$CK/server/alembic/versions" | sed 's/_.*//' | sort -n | tail -1)" = "0017"
# fresh DB upgrades to exactly 0017 — through the SUPPORTED
# settings environment; no startup adapter of any kind is
# permitted for certification
TMPROOT="$(mktemp -d)"
TMPDB="$TMPROOT/guard.db"
cd "$CK/server" && SOLORING_DATABASE_URL="sqlite:///$TMPDB" \
SOLORING_DATA_DIR="$TMPROOT" PYTHONDONTWRITEBYTECODE=1 \
python -m alembic upgrade head
test "$(python -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('SELECT version_num FROM alembic_version').fetchone()[0])" "$TMPDB")" = "0017_m16_intra_shot_consequences"
