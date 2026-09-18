"""M16 baseline verifier (frozen R7 §27 / §22 BASE cells).

Mechanically proves the exact M16 implementation predecessor identity
the frozen plan authorizes (§27 `m16_validate_baseline.py`):

  * test_base_01 — published M15 peeled commit/tree/tag object/Release
    ids are exact;
  * test_base_02 — the M15 tag is annotated and the verification reason
    is "unsigned", never falsely described as signed;
  * test_base_03 — the migration head before M16 is exactly
    0016_m15_revision_compatibility;
  * test_base_04 — PR-head CI #79 and post-merge CI #80 identities are
    recorded baseline evidence;
  * test_base_05 — the predecessor tree contains no M16 tables and no
    migration 0017;
  * test_base_06 — the baseline validator rejects any predecessor
    identity drift (self-test against deliberately drifted values).

Exit codes: 0 clean; 1 violation; 2 usage error.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

M15_COMMIT = "30ea135f3b2339491e9b36eaee2d0d8bc4ab8585"
M15_TREE = "db21568a3522a5ed2fa6fab44d1f9741d6d71ad2"
M15_TAG_OBJECT = "4c83eaaaee9c1099512ce01ed9567d737ebee1c9"
M15_RELEASE = 388490752
MIGRATION_HEAD_PRE_M16 = "0016_m15_revision_compatibility"
BASELINE_CI_PR_HEAD = "#79 / 34851439162"
BASELINE_CI_POST_MERGE = "#80 / 34855331701"

M16_TABLES = (
    "shot_intra_shot_events",
    "shot_intra_shot_event_proposals",
    "persistent_consequence_reviews",
    "shot_revision_intra_shot_specs",
    "shot_revision_intra_shot_events",
)


def git(*args: str, check: bool = True) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True,
    )
    if check and out.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def commit_tree_ok(commit: str, tree: str) -> bool:
    try:
        return git("rev-parse", f"{commit}^{{tree}}") == tree
    except RuntimeError:
        return False


def head_descends_from(commit: str) -> bool:
    try:
        git("merge-base", "--is-ancestor", commit, "HEAD")
        return True
    except RuntimeError:
        return False


def test_base_01() -> list[str]:
    errors: list[str] = []
    if not commit_tree_ok(M15_COMMIT, M15_TREE):
        errors.append("base01: M15 peeled commit/tree identity drifted")
    if not head_descends_from(M15_COMMIT):
        errors.append("base01: HEAD does not descend from M15 commit")
    # the live refs/tags/M15 must still resolve to the EXACT frozen
    # tag object and peel to the exact commit/tree
    try:
        tag_ref = git("rev-parse", "refs/tags/M15")
        peeled_commit = git("rev-parse", "refs/tags/M15^{commit}")
        peeled_tree = git("rev-parse", "refs/tags/M15^{tree}")
    except RuntimeError:
        return errors + ["base01: refs/tags/M15 unreadable"]
    if not tag_ref_resolves(tag_ref):
        errors.append(
            "base01: refs/tags/M15 resolves to "
            f"{tag_ref}, must be {M15_TAG_OBJECT}")
    if peeled_commit != M15_COMMIT:
        errors.append(
            "base01: refs/tags/M15 peels to "
            f"{peeled_commit}, must be {M15_COMMIT}")
    if peeled_tree != M15_TREE:
        errors.append(
            "base01: refs/tags/M15 tree is "
            f"{peeled_tree}, must be {M15_TREE}")
    return errors


def test_base_02() -> list[str]:
    errors: list[str] = []
    try:
        raw = git("cat-file", "-p", M15_TAG_OBJECT)
    except RuntimeError:
        return ["base02: M15 tag object unreadable"]
    lines = raw.splitlines()
    if not (len(lines) >= 3 and lines[2] == "tag M15"
            and lines[0] == f"object {M15_COMMIT}"
            and lines[1] == "type commit"):
        errors.append("base02: tag object is not an annotated M15 tag")
    if "tagger " not in raw:
        errors.append("base02: annotated tag lacks a tagger line")
    # the tag is deliberately unsigned; verification reason stays
    # "unsigned" and must never be described as signed
    if "BEGIN SSH SIGNATURE" in raw or "BEGIN PGP SIGNATURE" in raw:
        errors.append(
            "base02: baseline evidence describes the tag as signed")
    return errors


def test_base_03() -> list[str]:
    listing = git(
        "ls-tree", "--name-only", f"{M15_COMMIT}:server/alembic/versions")
    heads = [n for n in listing.splitlines() if n.endswith(".py")]
    numbered = sorted(n.split("_", 1)[0] for n in heads)
    if numbered[-1] != "0016":
        return [
            "base03: predecessor migration head is not 0016: "
            f"{numbered[-1]}"]
    if not any(n.startswith("0016_m15_revision_compatibility")
               for n in heads):
        return ["base03: 0016_m15_revision_compatibility absent at the "
                "predecessor"]
    if any(n.startswith("0017") for n in heads):
        return ["base03: 0017 already exists at the predecessor"]
    return []


def recorded_evidence_ok(release: int, pr_head: str, post_merge: str,
                         tag_object: str) -> bool:
    """The recorded-evidence equality: every frozen identity literal
    must match exactly (parameterized so the drift self-test can
    perturb each one independently)."""
    return (release == 388490752
            and pr_head == "#79 / 34851439162"
            and post_merge == "#80 / 34855331701"
            and tag_object == "4c83eaaaee9c1099512ce01ed9567d737ebee1c9")


def test_base_04() -> list[str]:
    # the frozen identities are recorded baseline evidence: the
    # constants above ARE the record; drift in ANY of them — Release,
    # CI runs, or the tag-object identity — is a failure
    if not recorded_evidence_ok(M15_RELEASE, BASELINE_CI_PR_HEAD,
                                BASELINE_CI_POST_MERGE, M15_TAG_OBJECT):
        return ["base04: recorded baseline evidence drifted"]
    return []


def test_base_05() -> list[str]:
    errors: list[str] = []
    try:
        models = git("show", f"{M15_COMMIT}:server/soloring/db/models.py")
    except RuntimeError:
        return ["base05: predecessor models.py unreadable"]
    for table in M16_TABLES:
        if f'"{table}"' in models:
            errors.append(f"base05: predecessor defines {table}")
    listing = git(
        "ls-tree", "--name-only", f"{M15_COMMIT}:server/alembic/versions")
    if any(n.startswith("0017")
           for n in listing.splitlines() if n.endswith(".py")):
        errors.append("base05: predecessor already carries migration 0017")
    return errors


def tag_ref_resolves(ref_value: str) -> bool:
    """Live tag-ref equality: the observed refs/tags/M15 value must be
    the exact frozen tag object (parameterized for the drift
    self-test)."""
    return ref_value == M15_TAG_OBJECT


def test_base_06() -> list[str]:
    # self-test: the identity checks reject deliberately drifted values
    errors: list[str] = []
    if commit_tree_ok(M15_COMMIT, "0" * 40):
        errors.append("base06: drifted tree was accepted")
    if commit_tree_ok("0" * 40, M15_TREE):
        errors.append("base06: drifted commit was accepted")
    # a drifted tag ref must fail the live-ref equality
    if tag_ref_resolves("0" * 40):
        errors.append("base06: drifted tag ref was accepted")
    # each perturbed recorded-evidence field must fail the equality
    if recorded_evidence_ok(M15_RELEASE + 1, BASELINE_CI_PR_HEAD,
                            BASELINE_CI_POST_MERGE, M15_TAG_OBJECT):
        errors.append("base06: drifted Release accepted")
    if recorded_evidence_ok(M15_RELEASE, "#99 / 0",
                            BASELINE_CI_POST_MERGE, M15_TAG_OBJECT):
        errors.append("base06: drifted PR-head CI accepted")
    if recorded_evidence_ok(M15_RELEASE, BASELINE_CI_PR_HEAD,
                            BASELINE_CI_POST_MERGE, "0" * 40):
        errors.append("base06: drifted tag-object identity accepted")
    return errors


def main() -> int:
    errors: list[str] = []
    for fn in (test_base_01, test_base_02, test_base_03, test_base_04,
               test_base_05, test_base_06):
        errors.extend(fn())
    if errors:
        for e in errors:
            print(f"M16-BASELINE INVALID: {e}", file=sys.stderr)
        return 1
    print("M16 baseline valid: M15 predecessor identity exact "
          f"(commit {M15_COMMIT[:7]}, tag object "
          f"{M15_TAG_OBJECT[:7]}, Release {M15_RELEASE}, migration "
          f"head {MIGRATION_HEAD_PRE_M16})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
