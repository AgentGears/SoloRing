
set -e
CERTIFYING_COMMIT=8199e46da6b8592f606725059601b402ab2874b0
CERTIFYING_TREE=941d14cda84d0186431a80c0f9cbdc3fa978296b
test "$(git -C "$CK" rev-parse HEAD)" = "$CERTIFYING_COMMIT"
test "$(git -C "$CK" rev-parse 'HEAD^{tree}')" = "$CERTIFYING_TREE"
test -z "$(git -C "$CK" status --porcelain --untracked-files=no)"
test -z "$(git -C "$CK" status --porcelain)"
test -z "$(git -C "$CK" diff-index --cached HEAD)"
test "$(ls "$CK/server/alembic/versions" | sed 's/_.*//' | sort -n | tail -1)" = "0017"
# no residue appeared inside the checkout during the run
test ! -e "$CK/m10f-scale-pkgs"
# general residue is already covered by the full --porcelain check above
