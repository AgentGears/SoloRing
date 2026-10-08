"""Storage-domain bounds (RR20-M17CC-01).

The ONE shared signed-SQLite-INTEGER authority bound, at the lowest
domain layer so every consumer — the public Shot authoring schemas
and the M16 canonical/recovery primitives alike — enforces the same
physical representability domain without depending upward on each
other. SQLite ``INTEGER`` columns store signed 64-bit integers, so
any integer the product asks SQLite to persist (or recovers from
durable authority and re-validates) must obey this bound; the
JS-safe ``SAFE_INT_MAX`` event-coordinate ceiling is a DIFFERENT
grammar law and deliberately lives with the event grammar.
"""

from __future__ import annotations

# The maximum signed SQLite INTEGER (2^63 - 1) — the physical storage
# authority domain's upper bound
SQLITE_INT_MAX = 9_223_372_036_854_775_807
