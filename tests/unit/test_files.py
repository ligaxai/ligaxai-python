"""``client.files`` and run ``attachments``: what is sent and parsed — sync and async alike."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest

from ligaxai import AsyncLigaX, LigaX
from ligaxai.resources.files import MAX_FILE_BYTES
from ligaxai.types import FileDeleted, FileObject
from tests.conftest import (
    PROFILE_ID,
    Recorder,
    error_body,
    frame,
    json_response,
    make_async_client,
    make_sync_client,
    run_body,
    sse,
    sse_response,
)

FILE_ID = "file_" + "F" * 24
OTHER_FILE_ID = "file_" + "G" * 24


def file_body(**overrides: Any) -> dict[str, Any]:
    """A complete ``FileObject`` as the server presents it (``present`` in ``files.ts``)."""
    body: dict[str, Any] = {
        "object": "file",
        "id": FILE_ID,
        "filename": "contract.pdf",
        "content_type": "application/pdf",
        "size_bytes": 11,
        "end_user_id": None,
        "created_at": "2026-10-22T08:00:00.000Z",
        "expires_at": "2026-11-21T08:00:00.000Z",
    }
    body.update(overrides)
    return body


async def call(client: LigaX | AsyncLigaX, dotted: str, *args: Any, **kwargs: Any) -> Any:
    target: Any = client
    for part in dotted.split("."):
        target = getattr(target, part)
    result = target(*args, **kwargs)
    if isinstance(client, AsyncLigaX):
        result = await result
    return result


ClientFactory = Callable[[Recorder], LigaX | AsyncLigaX]


@pytest.fixture(params=[make_sync_client, make_async_client], ids=["sync", "async"])
def factory(request: pytest.FixtureRequest) -> ClientFactory:
    return request.param  # type: ignore[no-any-return]


def parts_of(req: httpx2.Request) -> dict[str, tuple[dict[str, str], bytes]]:
    """Split a multipart body into ``{field: (part headers, content)}``."""
    ctype = req.headers["content-type"]
    assert ctype.startswith("multipart/form-data; boundary=")
    boundary = ctype.split("boundary=", 1)[1].encode()
    out: dict[str, tuple[dict[str, str], bytes]] = {}
    for chunk in req.content.split(b"--" + boundary)[1:-1]:
        # Each part is framed as "\r\n<headers>\r\n\r\n<content>\r\n".
        head, _, content = chunk.removeprefix(b"\r\n").partition(b"\r\n\r\n")
        content = content.removesuffix(b"\r\n")
        headers: dict[str, str] = {}
        for line in head.decode().split("\r\n"):
            key, _, value = line.partition(": ")
            headers[key.lower()] = value
        name = headers["content-disposition"].split('name="', 1)[1].split('"', 1)[0]
        out[name] = (headers, content)
    return out


# -- files.create ---------------------------------------------------------------------


async def test_create_from_path_sends_multipart(
    recorder: Recorder, factory: ClientFactory, tmp_path: Path
) -> None:
    path = tmp_path / "contract.pdf"
    path.write_bytes(b"%PDF-1.7 hi")
    recorder.responses = [json_response(201, file_body(), {"x-request-id": "req_f"})]
    created = await call(factory(recorder), "files.create", file=path)

    req = recorder.requests[0]
    assert req.method == "POST" and req.url.path == "/api/public/v1/files"
    parts = parts_of(req)
    assert set(parts) == {"file"}
    headers, content = parts["file"]
    assert 'filename="contract.pdf"' in headers["content-disposition"]
    assert headers["content-type"] == "application/pdf"
    assert content == b"%PDF-1.7 hi"
    assert isinstance(created, FileObject)
    assert created.id == FILE_ID and created.size_bytes == 11
    assert created.request_id == "req_f"


async def test_create_accepts_bytes_tuples_and_file_objects(
    recorder: Recorder, factory: ClientFactory, tmp_path: Path
) -> None:
    recorder.responses = [json_response(201, file_body())]
    client = factory(recorder)

    await call(client, "files.create", file=b"raw bytes")
    await call(client, "files.create", file=("notes.txt", b"hello"))
    await call(client, "files.create", file=("data.bin", b"\x00\x01", "application/x-custom"))
    path = tmp_path / "report.csv"
    path.write_bytes(b"a,b\n1,2\n")
    with path.open("rb") as fh:
        await call(client, "files.create", file=fh)
    await call(client, "files.create", file=io.BytesIO(b"in memory"))
    await call(client, "files.create", file=str(path))

    seen = [parts_of(r)["file"] for r in recorder.requests]
    disposition = [h["content-disposition"].split("filename=", 1)[1] for h, _ in seen]
    assert disposition == [
        '"upload"',
        '"notes.txt"',
        '"data.bin"',
        '"report.csv"',
        '"upload"',
        '"report.csv"',
    ]
    assert [h["content-type"] for h, _ in seen] == [
        "application/octet-stream",
        "text/plain",
        "application/x-custom",
        "text/csv",
        "application/octet-stream",
        "text/csv",
    ]
    assert [c for _, c in seen] == [
        b"raw bytes",
        b"hello",
        b"\x00\x01",
        b"a,b\n1,2\n",
        b"in memory",
        b"a,b\n1,2\n",
    ]


async def test_create_sends_end_user_id_as_a_form_field(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [json_response(201, file_body(end_user_id="user-42"))]
    created = await call(factory(recorder), "files.create", file=b"x", end_user_id="user-42")
    parts = parts_of(recorder.requests[0])
    assert set(parts) == {"file", "end_user_id"}
    assert parts["end_user_id"][1] == b"user-42"
    assert created.end_user_id == "user-42"


async def test_create_retry_resends_the_same_bytes(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    recorder.responses = [json_response(503), json_response(201, file_body())]
    await call(factory(recorder), "files.create", file=io.BytesIO(b"read once"))
    assert len(recorder.requests) == 2
    assert [parts_of(r)["file"][1] for r in recorder.requests] == [b"read once", b"read once"]


async def test_size_guard_refuses_before_any_request(
    recorder: Recorder, factory: ClientFactory, tmp_path: Path
) -> None:
    client = factory(recorder)
    too_big = b"\0" * (MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="at most 25 MB"):
        await call(client, "files.create", file=too_big)
    with pytest.raises(ValueError, match="at most 25 MB"):
        await call(client, "files.create", file=io.BytesIO(too_big))

    sparse = tmp_path / "huge.bin"
    with sparse.open("wb") as fh:  # a sparse file: the guard reads its size, not its bytes
        fh.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="at most 25 MB"):
        await call(client, "files.create", file=sparse)

    with pytest.raises(ValueError, match="empty"):
        await call(client, "files.create", file=b"")
    with pytest.raises(TypeError, match="binary mode"):
        await call(client, "files.create", file=io.StringIO("text"))
    assert recorder.requests == []


async def test_exactly_the_limit_is_accepted(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(201, file_body(size_bytes=MAX_FILE_BYTES))]
    await call(factory(recorder), "files.create", file=b"\0" * MAX_FILE_BYTES)
    assert len(parts_of(recorder.requests[0])["file"][1]) == MAX_FILE_BYTES


async def test_server_413_surfaces_as_status_error(
    recorder: Recorder, factory: ClientFactory
) -> None:
    from ligaxai import APIStatusError

    recorder.responses = [
        json_response(
            413,
            error_body("Files are limited to 25 MB.", type_="invalid_request_error"),
        )
    ]
    with pytest.raises(APIStatusError) as info:
        await call(factory(recorder), "files.create", file=b"x", options=None)
    assert info.value.status_code == 413
    assert len(recorder.requests) == 1


# -- files.get / files.delete ---------------------------------------------------------


async def test_get_and_delete(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(200, file_body()),
        json_response(200, {"object": "file", "id": FILE_ID, "deleted": True}),
    ]
    client = factory(recorder)
    got = await call(client, "files.get", FILE_ID)
    deleted = await call(client, "files.delete", FILE_ID)
    get_req, del_req = recorder.requests
    assert get_req.method == "GET" and get_req.url.path.endswith(f"/files/{FILE_ID}")
    assert del_req.method == "DELETE" and del_req.url.path.endswith(f"/files/{FILE_ID}")
    assert isinstance(got, FileObject) and got.filename == "contract.pdf"
    assert isinstance(deleted, FileDeleted) and deleted.deleted is True
    with pytest.raises(ValueError, match="file_id"):
        await call(client, "files.get", "")


# -- runs attachments -----------------------------------------------------------------


async def test_runs_create_and_wait_send_attachments(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [json_response(200, run_body())]
    client = factory(recorder)
    await call(client, "runs.create", profile_id=PROFILE_ID, input="Hi", attachments=[FILE_ID])
    await call(
        client,
        "runs.wait",
        profile_id=PROFILE_ID,
        input="Hi",
        attachments=(FILE_ID, OTHER_FILE_ID),
    )
    await call(client, "runs.create", profile_id=PROFILE_ID, input="Hi")
    bodies = [json.loads(r.content) for r in recorder.requests]
    assert bodies[0]["attachments"] == [FILE_ID]
    assert bodies[1]["attachments"] == [FILE_ID, OTHER_FILE_ID]
    assert "attachments" not in bodies[2]
    with pytest.raises(TypeError, match="list of file ids"):
        await call(client, "runs.create", profile_id=PROFILE_ID, input="Hi", attachments=FILE_ID)


def _stream_body() -> bytes:
    return sse([frame("run.end", 1, {"status": "completed"})])


def test_runs_stream_sends_attachments_sync(recorder: Recorder) -> None:
    recorder.responses = [sse_response(_stream_body())]
    with make_sync_client(recorder).runs.stream(
        profile_id=PROFILE_ID, input="Hi", attachments=[FILE_ID]
    ) as stream:
        list(stream)
    body = json.loads(recorder.requests[0].content)
    assert body["mode"] == "stream" and body["attachments"] == [FILE_ID]


async def test_runs_stream_sends_attachments_async(recorder: Recorder) -> None:
    recorder.responses = [sse_response(_stream_body(), is_async=True)]
    async with make_async_client(recorder).runs.stream(
        profile_id=PROFILE_ID, input="Hi", attachments=[FILE_ID]
    ) as stream:
        [e async for e in stream]
    body = json.loads(recorder.requests[0].content)
    assert body["mode"] == "stream" and body["attachments"] == [FILE_ID]
