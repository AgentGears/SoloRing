"""Regression laws for M17C transition route ownership."""

from soloring.api.main import app

_TARGETS = (
    ("POST", "/performance-candidates/{candidate_id}/adopt"),
    ("POST", "/performance-revisions/{revision_id}/retarget-candidates"),
)


def test_m17c_transition_path_method_pairs_have_one_runtime_owner():
    for method, path in _TARGETS:
        matches = [
            route
            for route in app.routes
            if getattr(route, "path", None) == path
            and method in (getattr(route, "methods", None) or set())
        ]
        assert len(matches) == 1, (method, path, matches)
        assert matches[0].endpoint.__module__ == "soloring.api.m17c_performance"


def test_m17c_transition_openapi_describes_the_runtime_owner():
    schema = app.openapi()
    for method, path in _TARGETS:
        operation = schema["paths"][path][method.lower()]
        assert "performance-m17c" in operation["tags"]
        assert "performance-m17b" not in operation["tags"]
