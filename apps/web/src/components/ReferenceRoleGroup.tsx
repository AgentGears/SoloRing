"use client";

// One visually grouped role (M2C §4.5): a flat cross-role order is never
// implied; move controls operate only inside this group.

import type { Asset, ReferenceItem } from "@/lib/types";
import ReferenceRow from "./ReferenceRow";

export default function ReferenceRoleGroup({
  role,
  references,
  assetsById,
  disabled,
  onMove,
  onRoleChange,
  onRemove,
}: {
  role: string;
  references: ReferenceItem[];
  assetsById: Map<string, Asset>;
  disabled: boolean;
  onMove: (assetId: string, role: string, delta: -1 | 1) => void;
  onRoleChange: (assetId: string, currentRole: string, role: string) => void;
  onRemove: (assetId: string, role: string) => void;
}) {
  return (
    <div className="role-group">
      <h3>
        <code>{role}</code> <span className="meta">({references.length})</span>
      </h3>
      {references.map((r, i) => (
        <ReferenceRow
          key={`${r.asset_id}:${r.role}`}
          reference={r}
          asset={assetsById.get(r.asset_id)}
          first={i === 0}
          last={i === references.length - 1}
          onMoveUp={() => onMove(r.asset_id, r.role, -1)}
          onMoveDown={() => onMove(r.asset_id, r.role, 1)}
          onRoleChange={(newRole) => onRoleChange(r.asset_id, r.role, newRole)}
          onRemove={() => onRemove(r.asset_id, r.role)}
          disabled={disabled}
        />
      ))}
    </div>
  );
}
