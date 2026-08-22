import io

# 2) Translator declares realization inputs (B4 core defect).
p = "server/soloring/executors/comfy/translate.py"
s = io.open(p, encoding="utf-8").read()
old = """    for key, decl in manifest.inputs.items():
        if decl.source_role is None:
            continue  # the prompt input: handled below, not a reference input
        declared_keys.add(key)"""
new = """    for key, decl in manifest.inputs.items():
        if (
            getattr(decl, "source_role", None) is None
            and not getattr(decl, "is_realization_input", False)
        ):
            continue  # the prompt input: handled below, not a reference input
        declared_keys.add(key)"""
assert s.count(old) == 1
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="").write(s)

# Bridge property on ManifestInputDefV2.
p = "server/soloring/workflows/manifest.py"
s = io.open(p, encoding="utf-8").read()
old = """        if isinstance(self.source, ShotReferenceSource):
            return self.source.role
        return None
"""
new = """        if isinstance(self.source, ShotReferenceSource):
            return self.source.role
        return None

    @property
    def is_realization_input(self) -> bool:
        \"\"\"B4 bridge: realization-channel inputs are reference-bearing
        inputs the translator must declare (they receive materialized
        bytes), unlike the prompt input.\"\"\"
        return isinstance(self.source, RealizationChannelSource)
"""
assert s.count(old) == 1
s = s.replace(old, new)

# 3) Zero-channel profiles are legal (zero realization inputs satisfy
# the bijection); the frozen text never requires >= 1 channel.
old = """    if not doc.channels:
        raise ProfileError("RealizationProfile declares no channels.")
"""
new = """    # Zero channels is a legal schema-1 shape: a package whose manifest
    # declares no realization inputs satisfies the §7.5 bijection vacuously
    # (the v2+empty-authority legacy lattice, §16.3).
"""
assert s.count(old) == 1
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="").write(s)

print("ok")
