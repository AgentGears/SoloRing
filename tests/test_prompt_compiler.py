"""Prompt compiler v1 tests (M2 plan §3.1, §6.1).

All expectations are asserted as explicit UTF-8 bytes; no platform newline
translation is involved.
"""

from __future__ import annotations

from soloring.domain.prompt import PROMPT_COMPILER_VERSION, compile_prompt
from soloring.domain.shot_intent import ShotIntent

FULL = ShotIntent(
    subject="Eva",
    action="enters the lobby",
    environment="hotel lobby",
    framing="medium wide",
    camera_motion="slow push-in",
    lens="50mm",
    mood="restrained unease",
    duration_ms=5000,
)

GOLDEN = (
    b"Subject: Eva\n"
    b"Action: enters the lobby\n"
    b"Environment: hotel lobby\n"
    b"Framing: medium wide\n"
    b"Camera Motion: slow push-in\n"
    b"Lens: 50mm\n"
    b"Mood: restrained unease"
)


def test_version_is_literal_one() -> None:
    assert PROMPT_COMPILER_VERSION == "1"


def test_golden_fixture_exact_bytes() -> None:
    assert compile_prompt(FULL).encode("utf-8") == GOLDEN


def test_deterministic_across_repeated_calls() -> None:
    assert compile_prompt(FULL) == compile_prompt(FULL)


def test_fixed_field_order_regardless_of_construction() -> None:
    a = ShotIntent(subject="s", mood="m", lens="l")
    b = ShotIntent(lens="l", mood="m", subject="s")
    assert compile_prompt(a) == compile_prompt(b) == (
        "Subject: s\nLens: l\nMood: m"
    )


def test_none_fields_skipped() -> None:
    out = compile_prompt(ShotIntent(subject="s", action=None, mood=None))
    assert out.encode("utf-8") == b"Subject: s"


def test_whitespace_only_optional_skipped_defensively() -> None:
    out = compile_prompt(ShotIntent(subject="s", action="   "))
    assert out.encode("utf-8") == b"Subject: s"


def test_subject_only() -> None:
    assert compile_prompt(ShotIntent(subject="Eva")).encode("utf-8") == b"Subject: Eva"


def test_duration_ms_does_not_affect_bytes() -> None:
    a = ShotIntent(subject="s", action="a", duration_ms=None)
    b = ShotIntent(subject="s", action="a", duration_ms=999999)
    assert compile_prompt(a) == compile_prompt(b)


# --- escaping matrix (§3.1.3) -----------------------------------------------


def test_backslash_escaping_exact() -> None:
    # input code points: C : \ r e f s \ e v a  -> each backslash doubles.
    out = compile_prompt(ShotIntent(subject="C:\\refs\\eva"))
    assert out == "Subject: C:\\\\refs\\\\eva"


def test_lf_escaping_exact() -> None:
    out = compile_prompt(ShotIntent(subject="enters the\nlobby"))
    assert out == "Subject: enters the\\nlobby"


def test_cr_escaping_exact() -> None:
    out = compile_prompt(ShotIntent(subject="a\rb"))
    assert out == "Subject: a\\rb"


def test_tab_escaping_exact() -> None:
    out = compile_prompt(ShotIntent(subject="a\tb"))
    assert out == "Subject: a\\tb"


def test_other_c0_and_del_escaping_exact() -> None:
    out = compile_prompt(ShotIntent(subject="a\x00b\x1fc\x7fd"))
    assert out == "Subject: a\\u0000b\\u001fc\\u007fd"


def test_lowercase_hex_escape() -> None:
    out = compile_prompt(ShotIntent(subject="x\x1b"))  # ESC
    assert out == "Subject: x\\u001b"
    out2 = compile_prompt(ShotIntent(subject="x\x0c"))  # form feed
    assert out2 == "Subject: x\\u000c"


def test_c1_controls_not_escaped() -> None:
    value = "a\u0080b\u009fc"  # C1 controls stay verbatim (plan §3.1.3)
    out = compile_prompt(ShotIntent(subject=value))
    assert out == "Subject: a\u0080b\u009fc"
    assert out.encode("utf-8") == b"Subject: a\xc2\x80b\xc2\x9fc"


def test_unicode_line_separators_not_escaped() -> None:
    value = "a\u2028b\u2029c"  # U+2028/U+2029 stay verbatim; only LF separates records
    out = compile_prompt(ShotIntent(subject=value))
    assert out == "Subject: a\u2028b\u2029c"
    assert out.encode("utf-8") == b"Subject: a\xe2\x80\xa8b\xe2\x80\xa9c"


def test_subject_emitted_verbatim_even_if_whitespace_only() -> None:
    # The defensive whitespace skip is for OPTIONAL fields only; the compiler
    # never redefines Shot normalization for the required subject (plan §3.1.1).
    out = compile_prompt(ShotIntent(subject="   "))
    assert out == "Subject:    "


def test_backslash_before_control_is_not_double_escaped() -> None:
    # One backslash + one LF must become "\\n" (3 chars), not "\\ + \n".
    out = compile_prompt(ShotIntent(subject="\\\n"))
    assert out == "Subject: \\\\\\n"


# --- Unicode preservation ----------------------------------------------------


def test_combining_characters_preserved_byte_distinct() -> None:
    nfc = compile_prompt(ShotIntent(subject="é"))  # U+00E9
    nfd = compile_prompt(ShotIntent(subject="e\u0301"))  # e + combining acute
    assert nfc != nfd
    assert nfc.encode("utf-8") == b"Subject: \xc3\xa9"
    assert nfd.encode("utf-8") == b"Subject: e\xcc\x81"


def test_long_value_stability() -> None:
    value = ("back\\slash and\nnewline " + "é" * 10) * 500  # ~ near subject bound
    a = compile_prompt(ShotIntent(subject=value))
    b = compile_prompt(ShotIntent(subject=value))
    assert a == b
    assert a.startswith("Subject: back\\\\slash and\\nnewline")


def test_no_trailing_newline_lf_only() -> None:
    out = compile_prompt(FULL)
    assert not out.endswith("\n")
    assert "\r" not in out
    assert out.count("\n") == 6  # seven records, six separators
