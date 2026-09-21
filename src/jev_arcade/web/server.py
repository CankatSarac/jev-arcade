"""A local viewer served from the standard library.

No web framework, because the zero dependency property of this repo is worth
more than the convenience. `http.server` streams Server Sent Events perfectly
well once you remember to flush after every event.

Security posture, since this process holds an API key:

* Binds to 127.0.0.1 by default. Not 0.0.0.0. Nothing outside this machine can
  reach it unless you deliberately pass a different host.
* The key never leaves the server. The browser receives game state and model
  answers, and never talks to TypeSafe directly.
* Every query parameter is checked against a fixed whitelist before use, and
  numbers are clamped, so a crafted URL cannot start an unbounded run.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jev_arcade.games.registry import available_games
from jev_arcade.players.jev_client import ENV_KEY
from jev_arcade.web.race import PLAYER_KINDS, race_frames

__all__ = ["serve", "RaceHandler", "MAX_TURNS_LIMIT"]

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
MAX_TURNS_LIMIT = 400  # hard cap, since every Jev turn costs an API call
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _clamp(value: str | None, low: float, high: float, fallback: float) -> float:
    try:
        return max(low, min(high, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


class RaceHandler(BaseHTTPRequestHandler):
    server_version = "jev-arcade"

    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug("%s %s", self.address_string(), fmt % args)

    # ---- helpers ---------------------------------------------------------

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: object, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

    # ---- routes ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        route = urlparse(self.path)
        if route.path in ("/", "/index.html"):
            return self._page()
        if route.path == "/api/config":
            return self._config()
        if route.path == "/api/race":
            return self._race(parse_qs(route.query))
        self._json({"error": "not found"}, 404)

    def _page(self) -> None:
        html = STATIC / "index.html"
        if not html.exists():
            return self._json({"error": "index.html is missing"}, 500)
        self._send(200, html.read_bytes(), "text/html; charset=utf-8")

    def _config(self) -> None:
        import os

        self._json(
            {
                "games": list(available_games()),
                "players": list(PLAYER_KINDS),
                # Reports only whether a key is present. Never its value.
                "jev_available": bool(os.environ.get(ENV_KEY, "").strip()),
                "env_key": ENV_KEY,
                "max_turns_limit": MAX_TURNS_LIMIT,
            }
        )

    def _race(self, query: dict[str, list[str]]) -> None:
        def first(name: str) -> str | None:
            values = query.get(name)
            return values[0] if values else None

        game = first("game") or "tetris"
        left = first("left") or "jev"
        right = first("right") or "heuristic"
        if (
            game not in available_games()
            or left not in PLAYER_KINDS
            or right not in PLAYER_KINDS
        ):
            return self._json({"error": "unknown game or player"}, 400)

        seed = int(_clamp(first("seed"), 0, 10**6, 0))
        max_turns = int(_clamp(first("max_turns"), 1, MAX_TURNS_LIMIT, 60))
        threshold = _clamp(first("threshold"), 0.0, 1.0, 0.0)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        # This stream is finite, unlike a typical SSE feed, and carries no
        # Content-Length. Closing the connection is the only thing that tells
        # the client the body ended, so keep-alive here hangs the reader.
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True

        try:
            for frame in race_frames(game, left, right, seed, max_turns, threshold):
                payload = json.dumps(frame, separators=(",", ":"))
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()  # without this the browser sees nothing
        except (BrokenPipeError, ConnectionResetError):
            logger.info("viewer disconnected, stopping the run")
        except Exception as exc:  # noqa: BLE001 - a crash here must not kill the server
            logger.exception("race failed")
            try:
                error = json.dumps({"type": "error", "message": str(exc)})
                self.wfile.write(f"data: {error}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the viewer. Blocks until interrupted."""
    try:
        httpd = _Server((host, port), RaceHandler)
    except OSError as exc:
        raise SystemExit(
            f"cannot bind {host}:{port} ({exc}). Try another port with --port."
        ) from exc

    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"WARNING: binding to {host} exposes this server beyond your machine, "
            "and it holds your TypeSafe API key."
        )
    print(f"jev-arcade viewer on http://{host}:{port}")
    print("press ctrl+c to stop")
    with httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
