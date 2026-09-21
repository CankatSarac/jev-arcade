"""A fake urlopen, so the suite never touches a network."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def ok(answers: dict[str, Any], model: str = "jev-1.13.0"):
    """An opener that always returns this answer set, recording each request."""
    calls: list[dict[str, Any]] = []

    def opener(request, timeout=None):
        calls.append(json.loads(request.data.decode("utf-8")))
        body = {"model": model, "answers": answers, "usage": {"input_tokens": 100}}
        return FakeResponse(json.dumps(body).encode("utf-8"))

    opener.calls = calls  # type: ignore[attr-defined]
    return opener


def http_error(code: int, then: Any = None):
    """An opener that fails with `code` once, then delegates to `then`."""
    state = {"failed": False}

    def opener(request, timeout=None):
        if not state["failed"]:
            state["failed"] = True
            raise urllib.error.HTTPError(
                url="https://api.typesafe.ai/v1/systemone",
                code=code,
                msg="boom",
                hdrs=None,
                fp=io.BytesIO(b"{}"),
            )
        if then is None:
            raise AssertionError("no follow up opener configured")
        return then(request, timeout=timeout)

    return opener


def always_http_error(code: int):
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(
            url="https://api.typesafe.ai/v1/systemone",
            code=code,
            msg="boom",
            hdrs=None,
            fp=io.BytesIO(b"{}"),
        )

    return opener
