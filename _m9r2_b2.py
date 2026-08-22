import io

# B2.1: normalize the M8 pack's target kind "feature" to the M9 rule
# vocabulary "feature_value" inside the adapter (one boundary).
p = "server/soloring/realization/authority.py"
s = io.open(p, encoding="utf-8").read()
old = """        target = anchor["target"]
        items = tuple("""
new = """        target = anchor["target"]
        # §7.3 (B2): the M8 pack encodes feature anchors as kind
        # "feature"; the M9 rule selector vocabulary is "feature_value".
        # Normalized ONCE here — the one adapter boundary — so captured
        # Feature authority matches exact feature_value rules.
        target_kind = target["kind"]
        if target_kind == "feature":
            target_kind = "feature_value"
        items = tuple("""
assert s.count(old) == 1
s = s.replace(old, new)

old = """        facets.append(CapturedFacet(
            visual_facet_id=fid,
            facet_key=anchor["facet_key"],
            requirement=requirement,
            target_kind=target["kind"],"""
new = """        facets.append(CapturedFacet(
            visual_facet_id=fid,
            facet_key=anchor["facet_key"],
            requirement=requirement,
            target_kind=target_kind,"""
assert s.count(old) == 1
s = s.replace(old, new)

# Also normalize inside the §10.1 rebuilt pack target on the way OUT is
# unnecessary (the pack keeps M8's own shape); only the authority value
# normalizes. But reconstruct compares rebuilt vs stored PACK (both M8
# shape) — unaffected.
io.open(p, "w", encoding="utf-8", newline="").write(s)

# B2.2: per-FACET channel-minimum omissions (multi-item facets emitted
# one omission per binding).
p = "server/soloring/realization/compiler.py"
s = io.open(p, encoding="utf-8").read()
old = """                # Optional-only channel below minimum: omit ALL its
                # optional facets, leave the channel inactive.
                for facet, _it in bindings:
                    omitted.append(OmittedOptional(
                        facet.visual_facet_id, facet.target_kind,
                        facet.facet_key, "channel_minimum_unmet",
                    ))
                    facet_channel.pop(facet.visual_facet_id, None)
                allocated[key] = []"""
new = """                # Optional-only channel below minimum: omit ALL its
                # optional facets (ONE omission per FACET, never per
                # binding), leave the channel inactive.
                seen_facets = {
                    facet.visual_facet_id for facet, _it in bindings
                }
                for facet, _it in bindings:
                    facet_channel.pop(facet.visual_facet_id, None)
                for facet in ordered:
                    if facet.visual_facet_id in seen_facets:
                        omitted.append(OmittedOptional(
                            facet.visual_facet_id, facet.target_kind,
                            facet.facet_key, "channel_minimum_unmet",
                        ))
                allocated[key] = []"""
assert s.count(old) == 1
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="").write(s)

print("ok")
