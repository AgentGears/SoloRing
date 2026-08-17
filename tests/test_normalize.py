"""Text normalization tests (plan §7, §50.4, §50.5)."""

from __future__ import annotations

from soloring.domain import normalize as n


# --- optional creative strings (§7.4) ---------------------------------------


def test_optional_creative_empty_becomes_none() -> None:
    assert n.normalize_optional_creative(None) is None
    assert n.normalize_optional_creative("") is None
    assert n.normalize_optional_creative("   ") is None


def test_optional_creative_nonempty_trimmed() -> None:
    assert n.normalize_optional_creative(" hi ") == "hi"
    assert n.normalize_optional_creative("walks") == "walks"


# --- required text: project name, shot subject (§7.1, §7.3) ----------------


def test_required_text_trims() -> None:
    assert n.normalize_required_text("  subj  ") == "subj"
    assert n.normalize_required_text("") == ""
    assert n.normalize_required_text(None) == ""
    assert n.normalize_required_text("   ") == ""  # caller must reject


# --- project description (§7.2) --------------------------------------------


def test_project_description_empty_to_none() -> None:
    assert n.normalize_project_description(None) is None
    assert n.normalize_project_description("  ") is None
    assert n.normalize_project_description("") is None


def test_project_description_trimmed() -> None:
    assert n.normalize_project_description("  a film ") == "a film"


# --- reference roles (§7.5, §11.4) -----------------------------------------


def test_role_structural_validity() -> None:
    # roles are exact/case-sensitive/untrimmed; only structurally validated.
    assert n.is_valid_role("reference")
    assert n.is_valid_role("Character")  # case preserved
    assert n.is_valid_role("reference ")  # trailing space is structurally legal
    assert n.is_valid_role("x" * 64)


def test_role_rejects_invalid() -> None:
    assert not n.is_valid_role("")
    assert not n.is_valid_role("   ")  # whitespace-only
    assert not n.is_valid_role("x" * 65)  # too long
    assert not n.is_valid_role(None)
    assert not n.is_valid_role(123)  # type: ignore[arg-type]


# --- original filename basename (§19) --------------------------------------


def test_basename_filename() -> None:
    assert n.basename_filename("/tmp/foo.png") == "foo.png"
    assert n.basename_filename("C:\\dir\\sub\\bar.jpg") == "bar.jpg"
    assert n.basename_filename("plain.png") == "plain.png"
    assert n.basename_filename(None) is None
    assert n.basename_filename("") is None
    assert len(n.basename_filename("a" * 600)) == n.ORIGINAL_FILENAME_MAX
