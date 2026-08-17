"""ComfyExecutor package (M5A; v0.1 §85-§90).

Everything Comfy-specific lives here, behind the GenerationExecutor boundary.
Nothing above this package learns node IDs, payload structure, client IDs,
queue representations, or history shapes.

M5A-2 layering: raw wire shapes are interpreted ONLY in wire.py; the closed
normalized models in models.py are the sole Comfy vocabulary above it; the
capability report in capabilities.py is versioned and evidence-backed.
"""
