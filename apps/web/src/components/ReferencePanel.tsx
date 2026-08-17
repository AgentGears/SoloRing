"use client";

// Reference panel (M2C §4.4-4.6). Every mutation — attach, remove, role
// change, reorder — emits the complete desired set to PUT and then adopts the
// server's normalized response as the new state; the client never invents
// final positions or recomputes creative identity. Move neighbors are
// computed strictly within one role. (asset_id, role) is the duplicate
// identity; the same asset under two roles is legal.

import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";

import {
  replaceReferences,
  uploadAsset,
} from "@/lib/api.client";
import { ApiError, asApiError } from "@/lib/api.shared";
import type { Asset, ReferenceItem } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";
import ReferenceRoleGroup from "./ReferenceRoleGroup";

export default function ReferencePanel({
  shotId,
  projectId,
  initialReferences,
  initialAssets,
}: {
  shotId: string;
  projectId: string;
  initialReferences: ReferenceItem[];
  initialAssets: Asset[];
}) {
  const router = useRouter();
  const [refs, setRefs] = useState<ReferenceItem[]>(initialReferences);
  const [assets, setAssets] = useState<Asset[]>(initialAssets);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [attachId, setAttachId] = useState("");
  const [attachRole, setAttachRole] = useState("reference");
  const fileInput = useRef<HTMLInputElement>(null);

  const assetsById = useMemo(
    () => new Map(assets.map((a) => [a.id, a])),
    [assets],
  );

  const groups = useMemo(() => {
    const byRole = new Map<string, ReferenceItem[]>();
    for (const r of refs) {
      const list = byRole.get(r.role) ?? [];
      list.push(r);
      byRole.set(r.role, list);
    }
    return [...byRole.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([role, list]) => ({
        role,
        references: [...list].sort((x, y) => x.position - y.position),
      }));
  }, [refs]);

  /** Send the full desired set; the PUT response is the canonical truth. */
  async function commit(desired: { asset_id: string; role: string }[]) {
    setBusy(true);
    setError(null);
    try {
      const normalized = await replaceReferences(shotId, desired);
      setRefs(normalized);
      router.refresh(); // working hash panel is server-rendered
    } catch (err) {
      setError(asApiError(err)); // displayed set stays consistent with server
    } finally {
      setBusy(false);
    }
  }

  function currentDesired(): { asset_id: string; role: string }[] {
    // Preserve canonical (role, position) order from server state.
    return [...refs]
      .sort((a, b) =>
        a.role === b.role ? a.position - b.position : a.role.localeCompare(b.role),
      )
      .map((r) => ({ asset_id: r.asset_id, role: r.role }));
  }

  function onMove(assetId: string, role: string, delta: -1 | 1) {
    const desired = currentDesired();
    // Swap with the adjacent neighbor WITHIN THE SAME ROLE only. The
    // occurrence is identified by the COMPLETE (asset_id, role) identity —
    // the same asset legally exists under several roles (audit F4).
    const idx = desired.findIndex(
      (d) => d.asset_id === assetId && d.role === role,
    );
    if (idx === -1) return;
    const sameRoleIdx = [];
    for (let i = 0; i < desired.length; i++) {
      if (desired[i].role === role) sameRoleIdx.push(i);
    }
    const posInRole = sameRoleIdx.indexOf(idx);
    const targetPos = posInRole + delta;
    if (targetPos < 0 || targetPos >= sameRoleIdx.length) return;
    const swapWith = sameRoleIdx[targetPos];
    [desired[idx], desired[swapWith]] = [desired[swapWith], desired[idx]];
    void commit(desired);
  }

  function onRoleChange(assetId: string, currentRole: string, newRole: string) {
    const trimmed = newRole.trim();
    if (!trimmed) return;
    // Remove ONLY the (asset_id, currentRole) occurrence; any other role the
    // same asset holds is untouched.
    const desired = currentDesired().filter(
      (d) => !(d.asset_id === assetId && d.role === currentRole),
    );
    // Append to the end of the destination role; the server re-normalizes
    // BOTH groups and the response is authoritative.
    desired.push({ asset_id: assetId, role: trimmed });
    void commit(desired);
  }

  function onRemove(assetId: string, role: string) {
    // Remove ONLY the (asset_id, role) occurrence.
    void commit(
      currentDesired().filter(
        (d) => !(d.asset_id === assetId && d.role === role),
      ),
    );
  }

  function attach() {
    if (!attachId || !attachRole.trim()) return;
    if (refs.some((r) => r.asset_id === attachId && r.role === attachRole.trim())) {
      setError(
        new ApiError(
          "REFERENCE_SET_INVALID",
          "This asset is already attached under that role.",
          400,
        ),
      );
      return;
    }
    const desired = currentDesired();
    desired.push({ asset_id: attachId, role: attachRole.trim() });
    setAttachId("");
    void commit(desired);
  }

  async function upload() {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const asset = await uploadAsset(projectId, file);
      setAssets((prev) => [...prev, asset]); // immediate rediscovery locally
      if (fileInput.current) fileInput.current.value = "";
      router.refresh(); // server-rendered asset list catches up
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}

      <div className="card form-row">
        <input
          ref={fileInput}
          type="file"
          aria-label="Reference file"
          disabled={busy}
        />
        <button className="btn" onClick={upload} disabled={busy}>
          {busy ? "Working…" : "Upload to project"}
        </button>
      </div>

      <div className="card form-row">
        <select
          value={attachId}
          onChange={(e) => setAttachId(e.target.value)}
          aria-label="Asset"
          disabled={busy || assets.length === 0}
        >
          <option value="">
            {assets.length === 0 ? "No project assets yet" : "Select asset…"}
          </option>
          {assets.map((a) => (
            <option key={a.id} value={a.id}>
              {(a.original_filename ?? "unnamed") +
                ` · ${a.blob_hash.slice(0, 8)}…`}
            </option>
          ))}
        </select>
        <input
          className="role-input"
          value={attachRole}
          onChange={(e) => setAttachRole(e.target.value)}
          aria-label="Role"
          maxLength={64}
        />
        <button
          className="btn"
          onClick={attach}
          disabled={busy || !attachId || !attachRole.trim()}
        >
          Attach
        </button>
      </div>

      {groups.length === 0 ? (
        <div className="empty">No references attached yet.</div>
      ) : (
        groups.map((g) => (
          <ReferenceRoleGroup
            key={g.role}
            role={g.role}
            references={g.references}
            assetsById={assetsById}
            disabled={busy}
            onMove={onMove}
            onRoleChange={onRoleChange}
            onRemove={onRemove}
          />
        ))
      )}
    </div>
  );
}
