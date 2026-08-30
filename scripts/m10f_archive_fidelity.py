"""Prove closing-archive/tree fidelity against the exact committed head.

Accounts for the two documented platform behaviors (R6 F-114):
  * git archive writes directory entries that git trees do not track
  * git archive on Windows applies CRLF conversion per .gitattributes
  * git quotes non-ASCII filenames with octal escapes in ls-tree output
"""
import subprocess
import sys
import zipfile


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
    for path, blob_sha in git_blobs.items():
        if path not in names:
            continue
        archive_content = z.read(path)
        blob = subprocess.run(
            ["git", "cat-file", "blob", blob_sha],
            capture_output=True).stdout
        if (archive_content.replace(b"\r\n", b"\n")
                != blob.replace(b"\r\n", b"\n")):
            mismatches += 1
            if mismatches <= 3:
                print(f"  MISMATCH: {path}")

    if mismatches == 0 and not missing and not extra:
        print("\nARCHIVE/TREE FIDELITY: EXACT")
        print("  file sets identical (incl. Unicode filenames)")
        print("  per-file content identical modulo documented CRLF")
        print("  conversion (F-114 platform behavior)")
        return 0
    print(f"\nFIDELITY ISSUES: {mismatches} content, "
          f"{len(missing)} missing, {len(extra)} extra")
    return 1


if __name__ == "__main__":
    sys.exit(main())
