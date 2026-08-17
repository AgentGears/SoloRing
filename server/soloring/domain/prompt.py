"""Prompt compiler v1 (v0.1 plan §35, M2 plan §3.1).

Pure, synchronous, deterministic. The module belongs to the creative domain;
executor and workflow packages may consume the persisted result later, but they
never own compiler behavior. Structural purity is enforced by an AST test
(tests/test_prompt_purity.py).

Version policy (plan §3.1.5): any change to output bytes for an existing input
requires a new PROMPT_COMPILER_VERSION. The golden byte fixtures fail on any
such change, forcing the bump.
"""

from __future__ import annotations

from soloring.domain.shot_intent import ShotIntent

# Literal module-level constant (plan §3.1). Never read from an environment
# variable, configuration file, database row, or mutable registry.
PROMPT_COMPILER_VERSION = "1"

# Fixed English protocol labels, fixed order (plan §3.1.2). duration_ms is
# deliberately absent: temporal metadata, not prompt content.
_FIELDS: tuple[tuple[str, str], ...] = (
    ("subject", "Subject"),
    ("action", "Action"),
    ("environment", "Environment"),
    ("framing", "Framing"),
    ("camera_motion", "Camera Motion"),
    ("lens", "Lens"),
    ("mood", "Mood"),
)

# Short escape forms applied before the generic C0/DEL rule (plan §3.1.3).
_SHORT_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\r", "\\r"),
    ("\n", "\\n"),
    ("\t", "\\t"),
)


def _escape_value(value: str) -> str:
    """Serialization escaping (plan §3.1.3). Persisted Shot text is unchanged.

    Order: (1) every literal backslash; (2) CR, LF, TAB; (3) remaining C0
    controls U+0000..U+001F and DEL U+007F as lowercase ``\\u00xx``. C1
    controls (U+0080..U+009F), U+2028, and U+2029 stay verbatim — only ASCII
    LF separates compiler records.
    """
    escaped = value.replace("\\", "\\\\")
    for ch, replacement in _SHORT_ESCAPES:
        escaped = escaped.replace(ch, replacement)
    out: list[str] = []
    for ch in escaped:
        cp = ord(ch)
        if cp <= 0x1F or cp == 0x7F:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(ch)
    return "".join(out)


def compile_prompt(intent: ShotIntent) -> str:
    """Compile a normalized ShotIntent into the v1 prompt string.

    Accepts normalized persisted intent: optional creative fields are ``None``
    rather than empty strings. The defensive whitespace-only skip applies to
    OPTIONAL fields only; ``subject`` (required) is emitted verbatim — the
    compiler never redefines Shot normalization. Output is LF-joined with no
    trailing newline.
    """
    lines: list[str] = []
    for field, label in _FIELDS:
        value = getattr(intent, field)
        if not isinstance(value, str):
            continue
        if field != "subject" and not value.strip():
            continue  # defensive guard, optional fields only (plan §3.1.1)
        lines.append(f"{label}: {_escape_value(value)}")
    return "\n".join(lines)
