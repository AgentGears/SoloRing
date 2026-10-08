"""Helpers for M17C-C capture tests: a tracked session factory bound to
the client's engine (the conftest make_tracked_maker pattern), so
capture_revision_with_visual can be called directly against the same
app state the HTTP surface uses."""

from tests.conftest import make_tracked_maker


def _factory(client):
    return make_tracked_maker(client._transport.app.state.engine)


async def capture(client, shot_id):
    from soloring.domain.revisions import capture_revision_with_visual
    return await capture_revision_with_visual(
        _factory(client)(), shot_id,
        settings=client._transport.app.state.settings)
