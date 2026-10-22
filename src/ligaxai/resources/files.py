"""``/files`` — upload a file for an agent to read, then attach it to a run (scope ``files:write``).

``create`` uploads one file (multipart field ``file``, up to 25 MB) and returns its
``file_…`` id; pass that id in ``runs.create(attachments=[…])`` (up to 10 per run). Files
are kept for 30 days, or until ``delete``. There is no download: a file exists for the
agent to read.

A client token uploads for its own end user, and only that user's runs can attach the file.
A secret key may name an ``end_user_id``.

The file is read into memory before the request is built, so a retry re-sends the same
bytes — a stream would be empty on the second attempt — and the 25 MB limit is checked here,
before any upload starts.
"""

from __future__ import annotations

import io
import mimetypes
import os
from pathlib import Path
from typing import IO, TypeAlias

import anyio.to_thread

from .._base_client import MultipartFiles
from .._generated.models import FileDeleted, FileObject
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, path_segment

__all__ = ["MAX_FILE_BYTES", "AsyncFiles", "FileInput", "Files"]

#: The platform's per-file limit (``MAX_FILE_BYTES`` in its ``files.ts``).
MAX_FILE_BYTES = 25 * 1024 * 1024

#: What ``files.create(file=…)`` accepts: a path, raw bytes (sent as ``upload``), a
#: ``(filename, bytes)`` or ``(filename, bytes, content_type)`` tuple, or a binary file
#: object opened for reading.
FileInput: TypeAlias = (
    str | os.PathLike[str] | bytes | tuple[str, bytes] | tuple[str, bytes, str] | IO[bytes]
)

_DEFAULT_NAME = "upload"
_DEFAULT_TYPE = "application/octet-stream"


def _too_large(size: int) -> ValueError:
    return ValueError(
        f"file is {size:,} bytes; the API accepts at most 25 MB ({MAX_FILE_BYTES:,} bytes) per file"
    )


def _guess_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or _DEFAULT_TYPE


def _read_capped(stream: IO[bytes]) -> bytes:
    # One byte past the limit is enough to know it is too large without reading it all.
    content = stream.read(MAX_FILE_BYTES + 1)
    if not isinstance(content, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("file objects must be opened in binary mode ('rb')")
    if len(content) > MAX_FILE_BYTES:
        raise _too_large(len(content))
    return content


def _load(file: FileInput) -> tuple[str, bytes, str]:
    """``file`` → ``(filename, content, content_type)``, refusing an empty or oversized file."""
    if isinstance(file, tuple):
        filename, content = file[0], file[1]
        content_type = file[2] if len(file) == 3 else _guess_type(filename)
    elif isinstance(file, bytes):
        filename, content, content_type = _DEFAULT_NAME, file, _DEFAULT_TYPE
    elif isinstance(file, str | os.PathLike):
        path = Path(file)
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise _too_large(size)
        with path.open("rb") as fh:
            content = _read_capped(fh)
        filename = path.name or _DEFAULT_NAME
        content_type = _guess_type(filename)
    elif isinstance(file, io.IOBase) or hasattr(file, "read"):
        content = _read_capped(file)
        raw_name = getattr(file, "name", None)
        filename = Path(raw_name).name if isinstance(raw_name, str) and raw_name else ""
        content_type = _guess_type(filename)
    else:
        raise TypeError(
            "file must be a path, bytes, a (filename, bytes[, content_type]) tuple or a "
            f"binary file object, not {type(file).__name__}"
        )
    if len(content) > MAX_FILE_BYTES:
        raise _too_large(len(content))
    if not content:
        raise ValueError("file is empty")
    return filename or _DEFAULT_NAME, content, content_type


def _form(
    file: tuple[str, bytes, str], end_user_id: str | None
) -> tuple[MultipartFiles, dict[str, str] | None]:
    return {"file": file}, ({"end_user_id": end_user_id} if end_user_id is not None else None)


def _file_path(file_id: str) -> str:
    return f"/files/{path_segment(file_id, 'file_id')}"


class Files(SyncAPIResource):
    def create(
        self,
        *,
        file: FileInput,
        end_user_id: str | None = None,
        options: RequestOptions | None = None,
    ) -> FileObject:
        """Upload one file for an agent to read; pass ``.id`` in ``runs.create(attachments=)``.

        Args:
            file: A path, bytes, ``(filename, bytes[, content_type])`` or a binary file
                object. Up to 25 MB — a larger file raises ``ValueError`` before any upload.
                The content type is guessed from the filename when not given.
            end_user_id: Secret keys only: the end user the file belongs to. A client token
                always uploads for its own user.
        """
        files, data = _form(_load(file), end_user_id)
        return self._client.request(
            "POST", "/files", cast_to=FileObject, files=files, data=data, options=options
        )

    def get(self, file_id: str, *, options: RequestOptions | None = None) -> FileObject:
        """A file's metadata (``file_…``). There is no download."""
        return self._client.request("GET", _file_path(file_id), cast_to=FileObject, options=options)

    def delete(self, file_id: str, *, options: RequestOptions | None = None) -> FileDeleted:
        """Delete a file before its 30-day expiry."""
        return self._client.request(
            "DELETE", _file_path(file_id), cast_to=FileDeleted, options=options
        )


class AsyncFiles(AsyncAPIResource):
    async def create(
        self,
        *,
        file: FileInput,
        end_user_id: str | None = None,
        options: RequestOptions | None = None,
    ) -> FileObject:
        """Upload one file for an agent to read. See :meth:`Files.create`.

        The file is read on a worker thread, so a large path does not block the event loop.
        """
        loaded = await anyio.to_thread.run_sync(_load, file)
        files, data = _form(loaded, end_user_id)
        return await self._client.request(
            "POST", "/files", cast_to=FileObject, files=files, data=data, options=options
        )

    async def get(self, file_id: str, *, options: RequestOptions | None = None) -> FileObject:
        """A file's metadata. See :meth:`Files.get`."""
        return await self._client.request(
            "GET", _file_path(file_id), cast_to=FileObject, options=options
        )

    async def delete(self, file_id: str, *, options: RequestOptions | None = None) -> FileDeleted:
        """Delete a file. See :meth:`Files.delete`."""
        return await self._client.request(
            "DELETE", _file_path(file_id), cast_to=FileDeleted, options=options
        )
