"""Typed continuity-value canonicalization (M7 plan §6–§8, frozen contract).

The server is the sole authority: clients submit ``value``; this module
validates the typed input, canonicalizes it, serializes the canonical
scalar through the ONE SoloRing canonical JSON serializer, and computes
the SHA-256 value hash. Binary float identity never participates; decimal
transport is string-only and parsed with Python ``Decimal``.

Frozen byte contracts (§7):

    boolean  true / false            (no integer coercion)
    enum     "fresh"                 (exact member, case preserved)
    integer  17  -4  0               (safe-integer bounds, no leading +)
    decimal  "1.5"                   (JSON string; trailing zeros stripped,
                                      -0 → "0", no exponent forms)
    text     exact validated string  (1–4096, caller-trimmed, no NFC/folding)

Every function is pure: no database access, no hidden normalization.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation

from soloring.domain.canonical import canonical_json_str

VALUE_TYPES: tuple[str, ...] = ("boolean", "enum", "integer", "decimal", "text")

# §7.3: cross-client safe-integer semantics.
SAFE_INTEGER_MIN = -9007199254740991
SAFE_INTEGER_MAX = 9007199254740991

# §7.4: frozen decimal limits — reject rather than round.
DECIMAL_MAX_PRECISION = 38
DECIMAL_MAX_SCALE = 18

# §7.5: text bounds.
TEXT_MAX = 4096

# §4.3 machine semantic key (features) and §37 predicate key share this.
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# §7.4 decimal transport grammar: optional '-', digits, optional .digits.
# Leading zeros ARE accepted transport ("00012.3400" is a listed example);
# rejected: exponents, '+', surrounding whitespace, empty parts, bare '.'.
_DECIMAL_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")


def is_valid_key(key: object) -> bool:
    """Feature/predicate machine key: [a-z][a-z0-9_]{0,63}."""
    return isinstance(key, str) and KEY_RE.match(key) is not None


def _invalid(value_type: str, reason: str):
    from soloring.errors import ErrorCode, SoloRingError

    return SoloRingError(
        ErrorCode.INVALID_CONTINUITY_VALUE,
        f"Invalid {value_type} continuity value: {reason}",
        status_code=422,
    )


def canonical_decimal_string(raw: str) -> str:
    """Plain decimal string with trailing fractional zeros stripped and
    negative zero collapsed (§7.4 examples, verbatim)."""
    d = Decimal(raw)
    sign, digits, exponent = d.as_tuple()
    if exponent >= 0:
        # Integer-valued: render digits, strip nothing, collapse -0.
        text = "".join(str(x) for x in digits) + "0" * exponent
        text = text.lstrip("0") or "0"
        return "-" + text if sign and text != "0" else text
    frac_len = -exponent
    all_digits = "".join(str(x) for x in digits)
    if len(all_digits) <= frac_len:
        int_part = "0"
        frac_part = "0" * (frac_len - len(all_digits)) + all_digits
    else:
        int_part = all_digits[:-frac_len]
        frac_part = all_digits[-frac_len:]
    int_part = int_part.lstrip("0") or "0"
    frac_part = frac_part.rstrip("0")
    if frac_part:
        text = f"{int_part}.{frac_part}"
    else:
        text = int_part
    return "-" + text if sign and text != "0" else text


def _validate_decimal_bounds(raw: str) -> None:
    d = Decimal(raw)
    if not d.is_finite():  # paranoia; grammar already rejects NaN/Infinity
        raise _invalid("decimal", "non-finite value")
    _, digits, exponent = d.as_tuple()
    precision = len(digits)
    scale = -exponent if exponent < 0 else 0
    if precision > DECIMAL_MAX_PRECISION:
        raise _invalid(
            "decimal",
            f"precision {precision} exceeds the frozen maximum of "
            f"{DECIMAL_MAX_PRECISION} digits",
        )
    if scale > DECIMAL_MAX_SCALE:
        raise _invalid(
            "decimal",
            f"scale {scale} exceeds the frozen maximum of {DECIMAL_MAX_SCALE}",
        )


def canonicalize_value(
    value_type: str,
    value: object,
    *,
    enum_values: list[str] | None = None,
) -> tuple[str, str]:
    """Validate + canonicalize one typed value.

    Returns ``(value_json, value_hash)`` where ``value_json`` is the exact
    canonical JSON serialization of the canonical scalar (§26) and
    ``value_hash`` is SHA-256 of its UTF-8 bytes. Raises the stable
    INVALID_CONTINUITY_VALUE (422) on any contract violation.
    """
    canonical: object
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise _invalid("boolean", "must be a JSON true/false")
        canonical = value

    elif value_type == "enum":
        if not isinstance(value, str):
            raise _invalid("enum", "must be a string")
        if enum_values is None or not enum_values:
            raise _invalid("enum", "feature declares no enum values")
        if value not in enum_values:
            raise _invalid(
                "enum", f"{value!r} is not an exact member of the enum"
            )
        canonical = value

    elif value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _invalid("integer", "must be a JSON integer (not boolean)")
        if not (SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX):
            raise _invalid(
                "integer",
                f"outside the safe-integer bounds "
                f"[{SAFE_INTEGER_MIN}, {SAFE_INTEGER_MAX}]",
            )
        canonical = value

    elif value_type == "decimal":
        if not isinstance(value, str):
            raise _invalid(
                "decimal", "transport must be a JSON string (never a float)"
            )
        if _DECIMAL_RE.match(value) is None:
            raise _invalid(
                "decimal",
                "must match -?digits[.digits] with no exponent, sign "
                "prefix, or surrounding whitespace",
            )
        try:
            Decimal(value)
        except InvalidOperation as exc:  # pragma: no cover - grammar guards
            raise _invalid("decimal", "unparseable") from exc
        _validate_decimal_bounds(value)
        canonical = canonical_decimal_string(value)

    elif value_type == "text":
        if not isinstance(value, str):
            raise _invalid("text", "must be a string")
        if not (1 <= len(value) <= TEXT_MAX):
            raise _invalid("text", f"length must be 1–{TEXT_MAX}")
        if value.strip() == "":
            raise _invalid("text", "must not be whitespace-only")
        if value != value.strip():
            raise _invalid(
                "text", "caller must provide already-trimmed input"
            )
        canonical = value

    else:
        raise _invalid(value_type or "unknown", "unknown value type")

    value_json = canonical_json_str(canonical)
    value_hash = hashlib.sha256(value_json.encode("utf-8")).hexdigest()
    return value_json, value_hash


def validate_enum_values(enum_values: object) -> list[str]:
    """Enum-list validation at Feature creation (§7.2).

    1–64 values, each 1–128 characters, non-empty, not whitespace-only,
    already trimmed, case-sensitive exact, duplicates forbidden, Unicode
    code points preserved with no normalization or folding. Returns the
    validated list in declaration order (order carries authoring meaning
    and is preserved in canonical storage).
    """
    from soloring.errors import ErrorCode, SoloRingError

    def bad(reason: str):
        return SoloRingError(
            ErrorCode.INVALID_CONTINUITY_FEATURE,
            f"Invalid enum values: {reason}",
            status_code=422,
        )

    if not isinstance(enum_values, list):
        raise bad("must be a list")
    if not (1 <= len(enum_values) <= 64):
        raise bad("must contain 1–64 values")
    seen: set[str] = set()
    for item in enum_values:
        if not isinstance(item, str):
            raise bad("each value must be a string")
        if not (1 <= len(item) <= 128):
            raise bad("each value must be 1–128 characters")
        if item.strip() == "":
            raise bad("values must not be whitespace-only")
        if item != item.strip():
            raise bad("values must already be trimmed")
        if item in seen:
            raise bad(f"duplicate value {item!r}")
        seen.add(item)
    return list(enum_values)
