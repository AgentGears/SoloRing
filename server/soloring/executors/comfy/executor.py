"""Comfy remote semantics: marker rediscovery (M5A-6; M5 plan §35-§38).

ComfyExecutor-level operations over the client. This layer knows how
submission/rediscovery works REMOTELY; it never touches the DB, worker
authority, or submission state (M5 amendment §3 split).

find_attempt merges queue + history evidence, groups by prompt_id, and
decides absent/adopt/duplicate — including the same-prompt-marker-conflict
case pinned by M5A-2's normalizer groundwork.
"""

from __future__ import annotations

from dataclasses import dataclass

from soloring.executors.comfy.client import ComfyAPIError, ComfyClient
from soloring.executors.comfy.models import SoloringMarker


class RediscoveryConflict(RuntimeError):
    """Duplicate attempt identity or conflicting same-prompt evidence."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


@dataclass(frozen=True)
class RediscoveryResult:
    outcome: str  # "absent" | "adopt"
    prompt_id: str | None = None


def _merge_evidence(
    queue_jobs, history_records, marker_pair: tuple[str, str]
) -> RediscoveryResult:
    """Merge normalized queue+history evidence for one attempt identity.

    Rules (M5 §35-§36, M5A-6 §7):
      * collect records whose marker matches the EXACT (generation, attempt);
      * group by prompt_id; one prompt visible in both surfaces counts once;
      * 0 unique → absent; 1 unique → adopt; >1 → COMFY_DUPLICATE_ATTEMPT;
      * the SAME prompt_id carrying DIFFERENT markers across surfaces is
        conflicting remote evidence → invariant failure (never merged).
    """
    generation_id, attempt_id = marker_pair
    # Every prompt's marker as seen on ANY surface — including NON-matching
    # identities: a prompt carrying two different SoloRing markers is
    # conflicting remote evidence regardless of which one is ours.
    seen_markers: dict[str, tuple | None] = {}
    ours: set[str] = set()

    def _consider(prompt_id: str, marker: SoloringMarker | None) -> None:
        pair = marker.as_pair() if marker else None
        if prompt_id in seen_markers and seen_markers[prompt_id] != pair:
            raise RediscoveryConflict(
                "conflicting_same_prompt_evidence",
                f"prompt {prompt_id} carries different SoloRing markers",
            )
        seen_markers[prompt_id] = pair
        if pair == marker_pair:
            ours.add(prompt_id)

    for job in queue_jobs:
        _consider(job.prompt_id, job.marker)
    for record in history_records.values():
        _consider(record.prompt_id, record.marker)

    unique = sorted(ours)
    if len(unique) == 0:
        return RediscoveryResult(outcome="absent")
    if len(unique) == 1:
        return RediscoveryResult(outcome="adopt", prompt_id=unique[0])
    raise RediscoveryConflict(
        "COMFY_DUPLICATE_ATTEMPT",
        f"attempt marker maps to {len(unique)} prompt_ids: {unique}",
    )


async def find_attempt(
    client: ComfyClient, generation_id: str, attempt_id: str
) -> RediscoveryResult:
    """One rediscovery iteration over the queue+history surfaces."""
    queue_jobs = await client.queue()
    history_records = await client.history()
    return _merge_evidence(queue_jobs, history_records, (generation_id, attempt_id))
