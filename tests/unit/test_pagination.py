from __future__ import annotations

import pytest

from base_project_module import AsyncPage, RequestOptions, SyncPage
from base_project_module._generated import ExampleModel
from base_project_module._pagination import PageRequest
from tests.conftest import Recorder, json_response, make_async_client, make_sync_client


def page_body(ids: list[str], next_page: str | None) -> dict[str, object]:
    return {"data": [{"id": i} for i in ids], "next_page": next_page}


def test_sync_pagination_walks_cursors(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(body=page_body(["a", "b"], "c2")),
        json_response(body=page_body(["c"], "c3")),
        json_response(body=page_body([], None)),
    ]
    client = make_sync_client(recorder)
    req = PageRequest("GET", "/things", options=RequestOptions(params={"limit": 2}))
    page = client.request_page(SyncPage[ExampleModel], req)
    assert page.has_next_page()
    assert [t.id for t in page.data] == ["a", "b"]
    assert page.request_id is None

    nxt = page.get_next_page()
    assert [t.id for t in nxt.data] == ["c"]
    assert recorder.requests[1].url.params["page"] == "c2"
    assert recorder.requests[1].url.params["limit"] == "2"

    last = nxt.get_next_page()
    assert not last.has_next_page()
    with pytest.raises(RuntimeError):
        last.get_next_page()


def test_sync_iter_auto_paginates(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(body=page_body(["a"], "c2")),
        json_response(body=page_body(["b"], None)),
    ]
    client = make_sync_client(recorder)
    page = client.request_page(SyncPage[ExampleModel], PageRequest("GET", "/things"))
    assert [t.id for t in page] == ["a", "b"]
    assert len(recorder.requests) == 2


def test_unbound_page_cannot_fetch() -> None:
    page: SyncPage[ExampleModel] = SyncPage[ExampleModel](
        data=[ExampleModel(id="x")], next_page="n"
    )
    assert page.has_next_page()
    with pytest.raises(RuntimeError):
        page.get_next_page()


async def test_async_pagination(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(body=page_body(["a"], "c2")),
        json_response(body=page_body(["b"], None)),
    ]
    client = make_async_client(recorder)
    page = await client.request_page(AsyncPage[ExampleModel], PageRequest("GET", "/things"))
    assert page.has_next_page()
    nxt = await page.get_next_page()
    assert [t.id for t in nxt.data] == ["b"]
    with pytest.raises(RuntimeError):
        await nxt.get_next_page()

    recorder.requests.clear()
    first = await client.request_page(AsyncPage[ExampleModel], PageRequest("GET", "/things"))
    assert [t.id async for t in first] == ["a", "b"]
    await client.close()
