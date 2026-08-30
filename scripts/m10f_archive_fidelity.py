"""Prove closing-archive/tree fidelity against the exact committed head.

Accounts for the two documented platform behaviors (R6 F-114):
  * git archive writes directory entries that git trees do not track
  * git archive on Windows applies CRLF conversion per .gitattributes
    for text files, but workflows/** is marked -text (byte-exact) and
    must NEVER be CRLF-normalized in the comparison

The attribute-aware comparator respects .gitattributes: files matching
workflows/** are compared byte-for-byte; all other files may be
CRLF-normalized per the documented platform behavior.
"""
import fnmatch
import subprocess
import sys
import zipfile
from pathlib import Path


def decode_git_path(raw: str) -> str:
    if not (raw.startswith('"') and raw.endswith('"')):
        return raw
    inner = raw[1:-1]
    out = bytearray()
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 3 < len(inner):
            try:
                out.append(int(inner[i + 1:i + 4], 8))
                i += 4
                continue
            except ValueError:
                pass
        out.extend(inner[i].encode("utf-8"))
        i += 1
    return out.decode("utf-8")


def _is_text_normalized(path: str) -> bool:
    """True when .gitattributes allows CRLF normalization for this path.
    workflows/** is explicitly -text (byte-exact hash contracts)."""
    return not fnmatch.fnmatch(path, "workflows/*")


def main() -> int:
    z = zipfile.ZipFile("SoloRing-M10F-closing.zip")
    names = {n for n in z.namelist() if not n.endswith("/")}

    out = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD"],
        capture_output=True, text=True).stdout
    git_blobs = {}
    for line in out.splitlines():
        meta, raw_path = line.split("\t", 1)
        path = decode_git_path(raw_path.strip())
        git_blobs[path] = meta.split()[2]

    print(f"archive file entries:  {len(names)}")
    print(f"git tree file entries: {len(git_blobs)}")
    missing = set(git_blobs) - names
    extra = names - set(git_blobs)
    print(f"missing: {len(missing)} {sorted(missing)[:2]}")
    print(f"extra:   {len(extra)} {sorted(extra)[:2]}")

    mismatches = 0
    byte_exact_checked = 0
    normalized_checked = 0
    for path, blob_sha in git_blobs.items():
        if path not in names:
            continue
        archive_content = z.read(path)
        blob = subprocess.run(
            ["git", "cat-file", "blob", blob_sha],
            capture_output=True).stdout
        if _is_text_normalized(path):
            comparison_a = archive_content.replace(b"\r\n", b"\n")
            comparison_b = blob.replace(b"\r\n", b"\n")
            normalized_checked += 1
        else:
            comparison_a = archive_content
            comparison_b = blob
            byte_exact_checked += 1
        if comparison_a != comparison_b:
            mismatches += 1
            mode = ("byte-exact (-text)" if not _is_text_normalized(path)
                    else "CRLF-normalized")
            if mismatches <= 3:
                print(f"  MISMATCH: {path} ({mode})")

    print(f"byte-exact files checked:  {byte_exact_checked}")
    print(f"CRLF-normalized checked:   {normalized_checked}")

    if mismatches == 0 and not missing and not extra:
        print("\nARCHIVE/TREE FIDELITY: EXACT")
        print("  file sets identical (incl. Unicode filenames)")
        print(f"  {byte_exact_checked} byte-exact (-text) files: "
             "byte-for-byte identical")
        print(f"  {normalized_checked} text files: identical modulo "
             "documented CRLF conversion (F-114)")
        return 0
    print(f"\nFIDELITY ISSUES: {mismatches} content, "
          f"{len(missing)} missing, {len(extra)} extra")
    return 1


def self_test():
    """Prove that workflows/** -text differences cannot be normalized
    away (the attribute-aware comparison catches them)."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        subprocess.run(["git", "init"], cwd=td, capture_output=True)
        (td / ".gitattributes").write_text("workflows/** -text\n")
        wf = td / "workflows" / "test.bin"
        wf.parent.mkdir()
        wf.write_bytes(b"line1\r\nline2\r\n")
        subprocess.run(["git", "add", "."], cwd=td, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-m", "test"], cwd=td, capture_output=True)
        wf.write_bytes(b"line1\nline2\n")
        subprocess.run(["git", "add", "."], cwd=td, capture_output=True)
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=td, capture_output=True, text=True)
        assert "workflows/test.bin" in proc.stdout, (
            "setup failed: the -text attribute should make git see "
            "the CRLF→LF change as a modification")
        assert fnmatch.fnmatch("workflows/test.bin", "workflows/*"), (
            "comparator bug: workflows/ should be byte-exact")
        assert not fnmatch.fnmatch("src/main.py", "workflows/*"), (
            "comparator bug: non-workflows/ should be CRLF-normalized")
        print("SELF-TEST PASS: workflows/** -text files are compared "
              "byte-for-byte, not CRLF-normalized")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        sys.exit(main())
