"""HTTP transport for the TypeSafe System One endpoint.

Standard library only. urllib is enough here because the retry policy is
written by hand anyway, and a zero dependency repo can be cloned and run with
nothing but python3.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any

__all__ = [
    "JevClient",
    "JevError",
    "JevAuthError",
    "JevTransportError",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
]

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
ENV_KEY = "TYPESAFE_API_KEY"

# 429 is rate limiting, 529 is the service reporting itself overloaded. Both
# are documented as retryable. Everything else is a real answer about the
# request and retrying it just wastes time.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})


class JevError(RuntimeError):
    """Any failure talking to the TypeSafe API."""


class JevAuthError(JevError):
    """The key was rejected. Never retried: a bad key stays bad."""


class JevTransportError(JevError):
    """Network trouble or repeated retryable failures."""


class JevClient:
    """Thin, synchronous client for a single evaluation endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 4,
        opener: Any = None,
    ) -> None:
        if not api_key:
            raise JevAuthError(f"no API key. Set {ENV_KEY} in the environment.")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        # Injected in tests so the suite never touches a network.
        self._opener = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls, **kwargs: Any) -> JevClient:
        """Build a client from TYPESAFE_API_KEY. The only supported key source."""
        key = os.environ.get(ENV_KEY, "").strip()
        if not key:
            raise JevAuthError(
                f"{ENV_KEY} is not set. Copy .env.example to .env and add your key, "
                "or export it in your shell."
            )
        model = kwargs.pop("model", os.environ.get("TYPESAFE_MODEL", DEFAULT_MODEL))
        base_url = kwargs.pop("base_url", os.environ.get("TYPESAFE_BASE_URL", DEFAULT_BASE_URL))
        return cls(api_key=key, model=model, base_url=base_url, **kwargs)

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], float]:
        """Send one batched evaluation. Returns the parsed body and latency in ms.

        Every question travels in a single request. TypeSafe documents parallel
        questions as much cheaper and faster than sequential calls, and a game
        loop that made three round trips per move would be three times slower
        for no benefit.
        """
        payload = json.dumps(
            {"state": state, "model": self.model, "questions": questions}
        ).encode("utf-8")

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            request = urllib.request.Request(
                self.base_url,
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "jev-arcade",
                },
            )
            started = time.perf_counter()
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return body, (time.perf_counter() - started) * 1000.0
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise JevAuthError(
                        "TypeSafe rejected the API key (401). Check TYPESAFE_API_KEY."
                    ) from exc
                if exc.code not in RETRYABLE_STATUS:
                    detail = self._safe_detail(exc)
                    raise JevError(f"TypeSafe returned {exc.code}: {detail}") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc

            if attempt < self.max_retries - 1:
                delay = (2**attempt) * 0.5 + random.random() * 0.25
                logger.warning(
                    "TypeSafe call failed (%s), retrying in %.2fs", last_error, delay
                )
                time.sleep(delay)

        raise JevTransportError(
            f"TypeSafe unreachable after {self.max_retries} attempts: {last_error}"
        )

    @staticmethod
    def _safe_detail(exc: urllib.error.HTTPError) -> str:
        """Read an error body without ever echoing the request, which holds the key."""
        try:
            return exc.read().decode("utf-8")[:400]
        except Exception:  # noqa: BLE001 - diagnostics must never mask the real error
            return exc.reason or "no detail"
