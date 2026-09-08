"use client";

import { useState } from "react";

import { PIStagingAuthoring } from "@/components/ProductionWorldPanel";

/** §25.3 reachability wrapper: the staging surface needs the exact
 *  occurrence whose PI subject owns the track — entered explicitly. */
export function PIStagingMount({ worldId }: { worldId: string }) {
  const [occurrenceId, setOccurrenceId] = useState("");
  const [committed, setCommitted] = useState<string | null>(null);
  return (
    <section aria-label="production instance staging mount">
      <label>
        Production Instance occurrence UUID
        <input
          value={occurrenceId}
          onChange={(e) => setOccurrenceId(e.target.value)}
          placeholder="occurrence UUID (production_instance subject)" />
      </label>{" "}
      <button
        type="button"
        disabled={occurrenceId.trim().length === 0}
        onClick={() => setCommitted(occurrenceId.trim())}>
        Load staging authoring
      </button>
      {committed ? (
        <PIStagingAuthoring worldId={worldId} occurrenceId={committed} />
      ) : (
        <small>
          {" "}Track creation requires the exact adopted occurrence;
          tracks belong to Production Instance subjects only.
        </small>
      )}
    </section>
  );
}
