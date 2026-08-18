"""ContinuityFeature service (M7A plan §4–§8, §19, §47).

Semantic fields are immutable after creation (§4.2): only name/description
are mutable display metadata, and renaming has no semantic side effect.
Keys are tombstone-inclusive unique per Entity and never recycled (§4.3).
All mutations are fenced BEGIN IMMEDIATE units with in-unit active-entity
verification (the M6A lesson), through monkeypatchable seams.
"""

from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _entity_not_found, _translate_op_error
from soloring.domain.canonical import canonical_json_str
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.normalize import normalize_optional_creative
from soloring.errors import ErrorCode, SoloRingError, validation_error
from soloring.continuity.values import (
    VALUE_TYPES,
    is_valid_key,
    validate_enum_values,
)

FEATURE_KINDS: tuple[str, ...] = (
    "injury", "surface_condition", "damage", "wardrobe_condition",
    "configuration", "status", "custom",
)

_COLUMNS = (
    "id, entity_id, key, kind, value_type, name, description, "
    "enum_values_json, unit, supersedes_feature_id, created_at, updated_at, "
    "deleted_at"
)


def _feature_not_found(feature_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.INVALID_CONTINUITY_FEATURE,
        f"ContinuityFeature {feature_id} not found.",
        status_code=404,
    )


async def _verify_active_feature(conn: AsyncConnection, feature_id: str) -> dict:
    """Active-feature check INSIDE a held BEGIN IMMEDIATE unit (test seam)."""
    row = (
        await conn.execute(
            text(
                "SELECT id, entity_id, key, kind, value_type, enum_values_json, "
                "unit, supersedes_feature_id FROM continuity_features "
                "WHERE id = :fid AND deleted_at IS NULL"
            ),
            {"fid": feature_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise _feature_not_found(feature_id)
    return dict(row)


def _validate_semantics(payload) -> dict:
    """Pure validation of the immutable semantic field set (§4–§8)."""
    key = payload.key
    if not is_valid_key(key):
        raise validation_error(
            f"Feature key {key!r} must match [a-z][a-z0-9_]{{0,63}}."
        )
    if payload.kind not in FEATURE_KINDS:
        raise SoloRingError(
            ErrorCode.INVALID_CONTINUITY_FEATURE,
            f"kind must be one of {FEATURE_KINDS}.",
            status_code=422,
        )
    if payload.value_type not in VALUE_TYPES:
        raise SoloRingError(
            ErrorCode.INVALID_CONTINUITY_FEATURE,
            f"value_type must be one of {VALUE_TYPES}.",
            status_code=422,
        )

    enum_values_json: str | None = None
    if payload.value_type == "enum":
        if payload.enum_values is None:
            raise SoloRingError(
                ErrorCode.INVALID_CONTINUITY_FEATURE,
                "enum value_type requires enum_values.",
                status_code=422,
            )
        enum_values = validate_enum_values(payload.enum_values)
        # Frozen contract §6: persist EXACT canonical serializer bytes,
        # declaration order preserved (distinct orders are distinct schemas).
        enum_values_json = canonical_json_str(enum_values)
    else:
        if payload.enum_values is not None:
            raise SoloRingError(
                ErrorCode.INVALID_CONTINUITY_FEATURE,
                "enum_values is only permitted for value_type=enum.",
                status_code=422,
            )

    unit = payload.unit
    if unit is not None:
        if payload.value_type not in ("integer", "decimal"):
            raise SoloRingError(
                ErrorCode.INVALID_CONTINUITY_FEATURE,
                "unit is only permitted for integer/decimal features.",
                status_code=422,
            )
        unit = unit.strip() if unit != unit.strip() else unit
        if not (1 <= len(unit) <= 64) or not unit.strip():
            raise SoloRingError(
                ErrorCode.INVALID_CONTINUITY_FEATURE,
                "unit must be 1–64 characters (already trimmed).",
                status_code=422,
            )

    name = (payload.name or "").strip()
    if not name:
        raise validation_error("Feature name must not be empty.")

    return {
        "key": key,
        "kind": payload.kind,
        "value_type": payload.value_type,
        "name": name,
        "description": normalize_optional_creative(payload.description),
        "enum_values_json": enum_values_json,
        "unit": unit,
        "supersedes_feature_id": payload.supersedes_feature_id,
    }


async def create_feature(session: AsyncSession, entity_id: str, payload) -> str:
    if not is_uuid(entity_id):
        raise _entity_not_found(entity_id)
    values = _validate_semantics(payload)
    feature_id = new_uuid()

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")

            entity = (
                await conn.execute(
                    text(
                        "SELECT id FROM creative_entities "
                        "WHERE id = :eid AND deleted_at IS NULL"
                    ),
                    {"eid": entity_id},
                )
            ).first()
            if entity is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise _entity_not_found(entity_id)

            # Tombstone-inclusive: a deleted key is never recycled (§4.3).
            existing_key = (
                await conn.execute(
                    text(
                        "SELECT id FROM continuity_features "
                        "WHERE entity_id = :eid AND key = :key"
                    ),
                    {"eid": entity_id, "key": values["key"]},
                )
            ).first()
            if existing_key is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_FEATURE_KEY_CONFLICT,
                    f"Entity already owns feature key {values['key']!r} "
                    "(keys are never recycled, including after deletion).",
                    status_code=409,
                )

            if values["supersedes_feature_id"] is not None:
                pred = (
                    await conn.execute(
                        text(
                            "SELECT id, entity_id FROM continuity_features "
                            "WHERE id = :pid"
                        ),
                        {"pid": values["supersedes_feature_id"]},
                    )
                ).first()
                if pred is None:
                    await conn.exec_driver_sql("ROLLBACK")
                    raise SoloRingError(
                        ErrorCode.CONTINUITY_FEATURE_SUPERSESSION_CONFLICT,
                        "supersedes_feature_id does not exist.",
                        status_code=409,
                    )
                if pred.entity_id != entity_id:
                    await conn.exec_driver_sql("ROLLBACK")
                    raise SoloRingError(
                        ErrorCode.CONTINUITY_FEATURE_SUPERSESSION_CONFLICT,
                        "supersession predecessor must belong to the same "
                        "Entity.",
                        status_code=409,
                    )
                # A second direct successor (active or tombstoned) is
                # rejected by the partial unique index; surface the stable
                # conflict code instead of a raw IntegrityError.
                claimed = (
                    await conn.execute(
                        text(
                            "SELECT 1 FROM continuity_features "
                            "WHERE supersedes_feature_id = :pid"
                        ),
                        {"pid": values["supersedes_feature_id"]},
                    )
                ).first()
                if claimed is not None:
                    await conn.exec_driver_sql("ROLLBACK")
                    raise SoloRingError(
                        ErrorCode.CONTINUITY_FEATURE_SUPERSESSION_CONFLICT,
                        "predecessor already has a direct successor "
                        "(lineage is single-successor for the Project "
                        "lifetime).",
                        status_code=409,
                    )

            await conn.execute(
                text(
                    "INSERT INTO continuity_features "
                    "(id, entity_id, key, kind, value_type, name, "
                    " description, enum_values_json, unit, "
                    " supersedes_feature_id, created_at, updated_at) "
                    "VALUES (:id, :eid, :key, :kind, :vt, :name, :desc, "
                    ":enum, :unit, :sup, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": feature_id,
                    "eid": entity_id,
                    "key": values["key"],
                    "kind": values["kind"],
                    "vt": values["value_type"],
                    "name": values["name"],
                    "desc": values["description"],
                    "enum": values["enum_values_json"],
                    "unit": values["unit"],
                    "sup": values["supersedes_feature_id"],
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "continuity feature creation") from exc
    return feature_id


async def list_features(session: AsyncSession, entity_id: str) -> list[dict]:
    if not is_uuid(entity_id):
        raise _entity_not_found(entity_id)
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM creative_entities "
                    "WHERE id = :eid AND deleted_at IS NULL"
                ),
                {"eid": entity_id},
            )
        ).first()
        if row is None:
            raise _entity_not_found(entity_id)
        rows = (
            await conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM continuity_features "
                    "WHERE entity_id = :eid AND deleted_at IS NULL "
                    "ORDER BY key"
                ),
                {"eid": entity_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]


async def get_feature(session: AsyncSession, feature_id: str) -> dict:
    if not is_uuid(feature_id):
        raise _feature_not_found(feature_id)
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM continuity_features "
                    "WHERE id = :fid AND deleted_at IS NULL"
                ),
                {"fid": feature_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise _feature_not_found(feature_id)
    return dict(row)


async def patch_feature(session: AsyncSession, feature_id: str, patch) -> None:
    """Display-metadata-only PATCH (§4.2): name/description, partial
    field-presence semantics (omitted → preserve; explicit null → clear)."""
    if not is_uuid(feature_id):
        raise _feature_not_found(feature_id)
    provided = patch.model_fields_set
    if not provided:
        await get_feature(session, feature_id)  # active check only
        return

    updates: dict[str, object] = {}
    if "name" in provided:
        name = (patch.name or "").strip()
        if not name:
            raise validation_error("Feature name must not be empty.")
        updates["name"] = name
    if "description" in provided:
        updates["description"] = normalize_optional_creative(patch.description)

    set_sql = ", ".join(f"{col} = :{col}" for col in updates)
    params = {**updates, "fid": feature_id}
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_feature(conn, feature_id)
            rowcount = (
                await conn.execute(
                    text(
                        "UPDATE continuity_features SET "
                        f"{set_sql}, updated_at = "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE id = :fid AND deleted_at IS NULL"
                    ),
                    params,
                )
            ).rowcount
            if rowcount != 1:
                await conn.exec_driver_sql("ROLLBACK")
                raise _feature_not_found(feature_id)
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "continuity feature patch") from exc


async def delete_feature(session: AsyncSession, feature_id: str) -> None:
    """Soft-delete; CONTINUITY_FEATURE_IN_USE while active transitions
    reference the Feature (§19). Idempotent. Historical
    ShotRevisionFeatureState rows never block deletion."""
    if not is_uuid(feature_id):
        raise _feature_not_found(feature_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT deleted_at FROM continuity_features "
                        "WHERE id = :fid"
                    ),
                    {"fid": feature_id},
                )
            ).first()
            if row is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise _feature_not_found(feature_id)
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent no-op
                return
            in_use = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM continuity_feature_transitions "
                        "WHERE feature_id = :fid AND deleted_at IS NULL "
                        "LIMIT 1"
                    ),
                    {"fid": feature_id},
                )
            ).first()
            if in_use is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_FEATURE_IN_USE,
                    f"ContinuityFeature {feature_id} has active transitions.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE continuity_features SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :fid"
                ),
                {"fid": feature_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(exc, "continuity feature deletion") from exc
