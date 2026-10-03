"""M17C-C first-pass-review correction (FPR-M17CC-04): capture the
mapping-document PREIMAGE on the schema-8 companion children.

The two captured mapping hashes (``performance_mapping_hash`` and
``vocal_mapping_hash``) were companion-only closure fields: excluded
from the frozen 11.2 embedded segment grammar and therefore from
``segment_json``/``segment_hash``, and unreconstructible from the
remaining captured or immutable columns — post-capture mutation of
either column was undetectable by section 12 reconstruction, section 13.4 recovery,
and reuse validation alike.

This successor adds exactly the three missing preimage columns to
``shot_revision_performance_segments`` so BOTH mapping documents
recompute as pure functions of the stored child row (plus nothing
else — no current-state read, honoring the section 12 law):

- ``vocal_mapping_position`` — the paired working vocal mapping's
  position (the one integer the performance mapping document carries
  that the child did not);
- ``vocal_performance_origin_num``/``vocal_performance_origin_den`` —
  the paired vocal mapping's own canonical rational performance origin
  (caller-supplied at its PUT and pinned by no law to the immutable
  binding's origin), joining the all-or-none vocal group.

The frozen section 11.2 embedded segment grammar and every snapshot byte law
are UNTOUCHED — the new columns are companion projection only, exactly
like the mapping hashes they anchor. No new Blob-FK path: the head's
physical inventory stays the fourteen paths of 0022. The downgrade
REFUSES when segments are populated (the preimage columns are captured
data, not recomputable), mirroring the 0022 populated fences.
"""

from alembic import op
import sqlalchemy as sa

revision = "0023_m17cc_capture_closure_preimage"
down_revision = "0022_m17c_schema8_capture"
branch_labels = None
depends_on = None

_TABLE = "shot_revision_performance_segments"

# FPR-M17CC-04: the all-or-none vocal group GROWS by the captured
# vocal-mapping preimage (origin + position)
_VOCAL_GROUP_ALL_OR_NONE = (
    "(vocal_performance_revision_id IS NULL "
    "AND vocal_binding_hash IS NULL "
    "AND vocal_mapping_hash IS NULL "
    "AND source_start_sample IS NULL "
    "AND source_end_sample_exclusive IS NULL "
    "AND sample_rate_hz IS NULL "
    "AND vocal_performance_origin_num IS NULL "
    "AND vocal_performance_origin_den IS NULL "
    "AND vocal_mapping_position IS NULL) OR "
    "(vocal_performance_revision_id IS NOT NULL "
    "AND vocal_binding_hash IS NOT NULL "
    "AND vocal_mapping_hash IS NOT NULL "
    "AND source_start_sample IS NOT NULL "
    "AND source_end_sample_exclusive IS NOT NULL "
    "AND sample_rate_hz IS NOT NULL "
    "AND vocal_performance_origin_num IS NOT NULL "
    "AND vocal_performance_origin_den IS NOT NULL "
    "AND vocal_mapping_position IS NOT NULL)"
)


def _create_segments() -> None:
    op.create_table(
        _TABLE,
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("performance_payload_blob_hash", sa.Text(),
                  nullable=False),
        sa.Column("performance_payload_sha256", sa.Text(),
                  nullable=False),
        sa.Column("performance_profile_id", sa.Text(), nullable=False),
        sa.Column("performance_kind", sa.Text(), nullable=False),
        sa.Column("performance_start_num", sa.Integer(), nullable=False),
        sa.Column("performance_start_den", sa.Integer(), nullable=False),
        sa.Column("performance_end_num", sa.Integer(), nullable=False),
        sa.Column("performance_end_den", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_num", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_den", sa.Integer(), nullable=False),
        sa.Column("performance_mapping_hash", sa.Text(), nullable=False),
        sa.Column("vocal_performance_revision_id", sa.String(36),
                  nullable=True),
        sa.Column("vocal_binding_hash", sa.Text(), nullable=True),
        sa.Column("vocal_mapping_hash", sa.Text(), nullable=True),
        sa.Column("source_start_sample", sa.Integer(), nullable=True),
        sa.Column("source_end_sample_exclusive", sa.Integer(),
                  nullable=True),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=True),
        sa.Column("vocal_performance_origin_num", sa.Integer(),
                  nullable=True),
        sa.Column("vocal_performance_origin_den", sa.Integer(),
                  nullable=True),
        sa.Column("vocal_mapping_position", sa.Integer(), nullable=True),
        sa.Column("segment_json", sa.Text(), nullable=False),
        sa.Column("segment_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_srpss_position"),
        sa.CheckConstraint(_VOCAL_GROUP_ALL_OR_NONE,
                           name="ck_srpss_vocal_group_all_or_none"),
        sa.CheckConstraint("length(performance_payload_blob_hash) = 64",
                           name="ck_srpss_payload_hash_len"),
        sa.CheckConstraint("length(vocal_binding_hash) = 64 OR "
                           "vocal_binding_hash IS NULL",
                           name="ck_srpss_binding_hash_len"),
        sa.CheckConstraint("length(segment_hash) = 64",
                           name="ck_srpss_segment_hash_len"),
        sa.CheckConstraint("vocal_mapping_position >= 0 OR "
                           "vocal_mapping_position IS NULL",
                           name="ck_srpss_vocal_position"),
        sa.CheckConstraint("vocal_performance_origin_den > 0 OR "
                           "vocal_performance_origin_den IS NULL",
                           name="ck_srpss_vocal_origin_den"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpss_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["performance_revision_id"], ["performance_revisions.id"],
            name="fk_srpss_pr", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_srpss_pr", _TABLE, ["performance_revision_id"])


def upgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(sa.text(
        f"SELECT COUNT(*) FROM {_TABLE}")).scalar()
    if existing:
        raise RuntimeError(
            f"0023 upgrade refused: {_TABLE} contains {existing} "
            "row(s) captured without the closure preimage — the "
            "preimage columns are CAPTURE data (written by the "
            "capture path), never backfilled by schema surgery; "
            "re-capture at the corrected head instead")
    op.drop_index("ix_srpss_pr", table_name=_TABLE)
    op.drop_table(_TABLE)
    _create_segments()


def downgrade() -> None:
    conn = op.get_bind()
    # the fence covers ALL THREE M17C-C tables: alembic commits each
    # migration step separately, so a segments-only fence would let the
    # destructive recreate run for a specs/GPI-only populate before the
    # 0022 fence fires downstream — the refusal must fire first
    for table in ("shot_revision_performance_specs",
                  "shot_revision_performance_segments",
                  "generation_performance_inputs"):
        n = conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0023 downgrade refused: {table} contains {n} row(s) "
                "whose captured closure preimage would be erased by "
                "schema downgrade")
    op.drop_index("ix_srpss_pr", table_name=_TABLE)
    op.drop_table(_TABLE)
    op.create_table(
        _TABLE,
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("performance_payload_blob_hash", sa.Text(),
                  nullable=False),
        sa.Column("performance_payload_sha256", sa.Text(),
                  nullable=False),
        sa.Column("performance_profile_id", sa.Text(), nullable=False),
        sa.Column("performance_kind", sa.Text(), nullable=False),
        sa.Column("performance_start_num", sa.Integer(), nullable=False),
        sa.Column("performance_start_den", sa.Integer(), nullable=False),
        sa.Column("performance_end_num", sa.Integer(), nullable=False),
        sa.Column("performance_end_den", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_num", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_den", sa.Integer(), nullable=False),
        sa.Column("performance_mapping_hash", sa.Text(), nullable=False),
        sa.Column("vocal_performance_revision_id", sa.String(36),
                  nullable=True),
        sa.Column("vocal_binding_hash", sa.Text(), nullable=True),
        sa.Column("vocal_mapping_hash", sa.Text(), nullable=True),
        sa.Column("source_start_sample", sa.Integer(), nullable=True),
        sa.Column("source_end_sample_exclusive", sa.Integer(),
                  nullable=True),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=True),
        sa.Column("segment_json", sa.Text(), nullable=False),
        sa.Column("segment_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_srpss_position"),
        sa.CheckConstraint(
            "(vocal_performance_revision_id IS NULL "
            "AND vocal_binding_hash IS NULL "
            "AND vocal_mapping_hash IS NULL "
            "AND source_start_sample IS NULL "
            "AND source_end_sample_exclusive IS NULL "
            "AND sample_rate_hz IS NULL) OR "
            "(vocal_performance_revision_id IS NOT NULL "
            "AND vocal_binding_hash IS NOT NULL "
            "AND vocal_mapping_hash IS NOT NULL "
            "AND source_start_sample IS NOT NULL "
            "AND source_end_sample_exclusive IS NOT NULL "
            "AND sample_rate_hz IS NOT NULL)",
            name="ck_srpss_vocal_group_all_or_none"),
        sa.CheckConstraint("length(performance_payload_blob_hash) = 64",
                           name="ck_srpss_payload_hash_len"),
        sa.CheckConstraint("length(vocal_binding_hash) = 64 OR "
                           "vocal_binding_hash IS NULL",
                           name="ck_srpss_binding_hash_len"),
        sa.CheckConstraint("length(segment_hash) = 64",
                           name="ck_srpss_segment_hash_len"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpss_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["performance_revision_id"], ["performance_revisions.id"],
            name="fk_srpss_pr", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_srpss_pr", _TABLE, ["performance_revision_id"])
