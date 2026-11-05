"""The frozen-watchlist loader reports every read failure as WatchlistUnavailableError."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from nitro_utils import s3_loader
from nitro_utils.s3_loader import WatchlistUnavailableError, _load_from_s3_sync

if TYPE_CHECKING:
    from collections.abc import Callable


class _FakeS3:
    def __init__(
        self,
        *,
        list_error: Exception | None = None,
        get_error: Exception | None = None,
        body: bytes = b"a,b\n1,2\n",
        listed: bool = True,
    ) -> None:
        self._list_error = list_error
        self._get_error = get_error
        self._body = body
        self._listed = listed

    def list_objects_v2(self, **_kwargs: Any) -> dict[str, Any]:
        if self._list_error:
            raise self._list_error
        return {"Contents": [{"Key": "k"}]} if self._listed else {}

    def get_object(self, **_kwargs: Any) -> dict[str, Any]:
        if self._get_error:
            raise self._get_error
        return {"Body": io.BytesIO(self._body)}


def _client_error(operation: str) -> ClientError:
    return ClientError({"Error": {"Code": "InvalidAccessKeyId", "Message": "bad key"}}, operation)


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _FakeS3) -> None:
    monkeypatch.setattr(s3_loader.boto3, "client", lambda *_a, **_k: fake)


def test_reads_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeS3())
    assert _load_from_s3_sync("k") == [{"a": "1", "b": "2"}]


def test_missing_artifact_is_an_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeS3(listed=False))
    assert _load_from_s3_sync("k") == []


@pytest.mark.parametrize(
    "fake_factory",
    [
        lambda: _FakeS3(list_error=_client_error("ListObjectsV2")),
        lambda: _FakeS3(list_error=NoCredentialsError()),
        lambda: _FakeS3(get_error=_client_error("GetObject")),
        lambda: _FakeS3(get_error=NoCredentialsError()),
        lambda: _FakeS3(body=b"\xff\xfe\x00"),
    ],
    ids=["list-client", "list-no-credentials", "get-client", "get-no-credentials", "bad-utf8"],
)
def test_every_read_failure_is_watchlist_unavailable(
    monkeypatch: pytest.MonkeyPatch, fake_factory: Callable[[], _FakeS3]
) -> None:
    _patch(monkeypatch, fake_factory())
    with pytest.raises(WatchlistUnavailableError):
        _load_from_s3_sync("k")


def test_unexpected_errors_are_not_disguised(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeS3(get_error=KeyError("boom")))
    with pytest.raises(KeyError):
        _load_from_s3_sync("k")
