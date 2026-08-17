"use client";

// One reference row inside a role group (M2C §4.5-4.6). All mutations are
// expressed by the parent as full-set intents; this component only reports
// intents (move up/down within the role, role change, remove).

import { useState } from "react";

import { toBlobUrl } from "@/lib/api.client";
import type { Asset, ReferenceItem } from "@/lib/types";

export default function ReferenceRow({
  reference,
  asset,
  first,
  last,
  onMoveUp,
  onMoveDown,
  onRoleChange,
  onRemove,
  disabled,
}: {
  reference: ReferenceItem;
  asset: Asset | undefined;
  first: boolean;
  last: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRoleChange: (role: string) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  const [roleDraft, setRoleDraft] = useState(reference.role);

  const isImage =
    asset?.detected_media_type === "image/png" ||
    asset?.detected_media_type === "image/jpeg";
  const thumbUrl =
    isImage && asset ? toBlobUrl(asset.blob_url) : null;

  return (
    <div className="ref-row">
      {thumbUrl ? (
        <img src={thumbUrl} alt={asset?.original_filename ?? "reference"} />
      ) : (
        <div className="generic-icon">FILE</div>
      )}
      <div className="ref-meta">
        <div className="name">
          {asset?.original_filename ?? `asset ${reference.asset_id.slice(0, 8)}…`}
        </div>
        <div className="meta">
          {asset ? `${asset.blob_hash.slice(0, 8)}… · ${asset.detected_media_type ?? "unknown type"}` : "metadata unavailable"}
        </div>
      </div>
      <div className="ref-controls">
        <button
          className="btn btn-small"
          onClick={onMoveUp}
          disabled={disabled || first}
          aria-label="Move up within role"
        >
          ↑
        </button>
        <button
          className="btn btn-small"
          onClick={onMoveDown}
          disabled={disabled || last}
          aria-label="Move down within role"
        >
          ↓
        </button>
        <input
          className="role-input"
          value={roleDraft}
          onChange={(e) => setRoleDraft(e.target.value)}
          aria-label="Role"
          maxLength={64}
        />
        <button
          className="btn btn-small"
          onClick={() => onRoleChange(roleDraft)}
          disabled={disabled || roleDraft === reference.role}
        >
          Move role
        </button>
        <button
          className="btn btn-danger btn-small"
          onClick={onRemove}
          disabled={disabled}
        >
          Remove
        </button>
      </div>
    </div>
  );
}
