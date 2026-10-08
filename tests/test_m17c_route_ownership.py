"""Regression laws for M17C transition route ownership."""

from soloring.api.main import app

_TARGETS = (
    ("POST", "/performance-candidates/{candidate_id}/adopt"),
    ("POST", "/performance-revisions/{revision_id}/retarget-candidates"),
)


def _effective_routes(routes):
    """Yield resolved routes regardless of the FastAPI router model.

    FastAPI >= 0.141 keeps included routers as lazy _IncludedRouter
    wrappers (no ``path`` attribute) whose routes resolve through
    ``effective_candidates()``; older versions flatten plain routes
    directly. Walking both shapes keeps this proof meaningful across
    the lazy-router transition instead of seeing zero routes.
    """
    for route in routes:
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            yield from _effective_routes(candidates())
            continue
        yield route


def _route_methods(route) -> set:
    methods = getattr(route, "methods", None)
    if methods is None:
        original = getattr(route, "original_route", None)
        methods = getattr(original, "methods", None)
    return methods or set()


def test_m17c_transition_path_method_pairs_have_one_runtime_owner():
    for method, path in _TARGETS:
        matches = [
            route
            for route in _effective_routes(app.routes)
            if getattr(route, "path", None) == path
            and method in _route_methods(route)
        ]
        assert len(matches) == 1, (method, path, matches)
        endpoint = matches[0].endpoint
        assert endpoint.__module__ == "soloring.api.m17c_performance"


def test_m17c_transition_openapi_describes_the_runtime_owner():
    schema = app.openapi()
    for method, path in _TARGETS:
        operation = schema["paths"][path][method.lower()]
        assert "performance-m17c" in operation["tags"]
        assert "performance-m17b" not in operation["tags"]
