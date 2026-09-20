"""Canonical rational primitives for M17A exact temporal mapping
(frozen R5 §6.1).

Every persisted rational is a canonical-reduced signed/positive
integer pair; 0 is always 0/1. Intermediate arithmetic detects
signed-64-bit persistence overflow and fails rather than wraps. No
floating-point value participates in authority.
"""

from __future__ import annotations

import math
from fractions import Fraction

from soloring.errors import SoloRingError, ErrorCode

_I64_MIN = -(2 ** 63)
_I64_MAX = 2 ** 63 - 1


class RationalError(SoloRingError):
    def __init__(self, reason: str):
        super().__init__(
            ErrorCode.INVALID_RATIONAL,
            f"INVALID_RATIONAL: {reason}",
            status_code=422,
            details={"reason": reason},
        )


def canonical_rational(num: int, den: int) -> tuple[int, int]:
    """Reduce (num, den) to the canonical persisted form (frozen §6.1 /
    mandatory E06: reducible caller input canonicalizes BEFORE
    persistence and hashing — 2/4 -> 1/2, 0/99 -> 0/1). Per the
    mandatory-matrix ruling recorded in the second source review:
    den <= 0 REJECTS (latent §6.1 -2/-4 note notwithstanding); E06
    reduction applies to reducible positive-denominator inputs."""
    if not isinstance(num, int) or not isinstance(den, int):
        raise RationalError("numerator and denominator must be integers")
    if den <= 0:
        raise RationalError("denominator must be positive")
    g = math.gcd(abs(num), den)
    if g != 1:
        num //= g
        den //= g
    if num == 0:
        den = 1
    _check_i64(num, "numerator")
    _check_i64(den, "denominator")
    return num, den


def canonical_fraction(num: int, den: int) -> Fraction:
    n, d = canonical_rational(num, den)
    return Fraction(n, d)


def fraction_to_persisted(f: Fraction) -> tuple[int, int]:
    return canonical_rational(f.numerator, f.denominator)


def _check_i64(v: int, what: str) -> None:
    if not (_I64_MIN <= v <= _I64_MAX):
        raise RationalError(
            f"{what} {v} outside signed 64-bit persistence range")


def performance_ms(sample: int, *, origin_num: int, origin_den: int,
                   source_start_sample: int,
                   sample_rate_hz: int) -> Fraction:
    """performance_ms(s) = origin + ((s - start) * 1000 / rate)."""
    delta = (sample - source_start_sample) * 1000
    f = Fraction(delta, sample_rate_hz) + Fraction(origin_num, origin_den)
    _check_i64(f.numerator, "performance_ms numerator")
    _check_i64(f.denominator, "performance_ms denominator")
    return f


def shot_ms(sample: int, *, anchor_num: int, anchor_den: int,
            source_start_sample: int,
            sample_rate_hz: int) -> Fraction:
    """shot_ms(s) = anchor + ((s - start) * 1000 / rate)."""
    delta = (sample - source_start_sample) * 1000
    f = Fraction(delta, sample_rate_hz) + Fraction(anchor_num, anchor_den)
    _check_i64(f.numerator, "shot_ms numerator")
    _check_i64(f.denominator, "shot_ms denominator")
    return f
