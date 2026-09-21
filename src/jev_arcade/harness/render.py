"""Terminal rendering, so you can watch a game being played.

Plain ANSI escapes and box drawing characters. No dependency, works over ssh.
"""

from __future__ import annotations

from typing import Any

__all__ = ["render", "clear_screen"]

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"

TILE_COLOURS = {
    0: "\x1b[48;5;236m",
    2: "\x1b[48;5;250m\x1b[30m",
    4: "\x1b[48;5;180m\x1b[30m",
    8: "\x1b[48;5;215m\x1b[30m",
    16: "\x1b[48;5;209m",
    32: "\x1b[48;5;203m",
    64: "\x1b[48;5;196m",
    128: "\x1b[48;5;227m\x1b[30m",
    256: "\x1b[48;5;226m\x1b[30m",
    512: "\x1b[48;5;220m\x1b[30m",
    1024: "\x1b[48;5;214m\x1b[30m",
    2048: "\x1b[48;5;208m",
}


def clear_screen() -> str:
    return "\x1b[2J\x1b[H"


def render(state: dict[str, Any], game_name: str) -> str:
    if game_name == "tetris":
        return _render_tetris(state)
    if game_name == "snake":
        return _render_snake(state)
    if game_name == "2048":
        return _render_2048(state)
    return repr(state)


def _render_tetris(state: dict[str, Any]) -> str:
    lines = [f"{BOLD}TETRIS{RESET}   score {state['score']}   lines {state['lines_cleared']}"]
    lines.append(f"{DIM}piece {state['current_piece']}  next {state['next_piece']}  "
                 f"holes {state['holes']}{RESET}")
    lines.append("┌" + "─" * (state["width"] * 2) + "┐")
    for row in state["board"]:
        cells = "".join("██" if ch == "#" else f"{DIM}··{RESET}" for ch in row)
        lines.append("│" + cells + "│")
    lines.append("└" + "─" * (state["width"] * 2) + "┘")
    return "\n".join(lines)


def _render_snake(state: dict[str, Any]) -> str:
    lines = [f"{BOLD}SNAKE{RESET}   score {state['score']}   length {state['body_length']}"]
    lines.append("┌" + "─" * (state["size"] * 2) + "┐")
    glyphs = {"H": "\x1b[92m██\x1b[0m", "o": "\x1b[32m▓▓\x1b[0m", "*": "\x1b[91m ●\x1b[0m"}
    for row in state["grid"]:
        lines.append("│" + "".join(glyphs.get(ch, f"{DIM}··{RESET}") for ch in row) + "│")
    lines.append("└" + "─" * (state["size"] * 2) + "┘")
    return "\n".join(lines)


def _render_2048(state: dict[str, Any]) -> str:
    lines = [f"{BOLD}2048{RESET}   score {state['score']}   best tile {state['max_tile']}"]
    lines.append("┌" + "─" * (state["size"] * 6) + "┐")
    for row in state["grid"]:
        cells = ""
        for value in row:
            colour = TILE_COLOURS.get(value, "\x1b[48;5;202m")
            label = "" if value == 0 else str(value)
            cells += f"{colour}{label:^6}{RESET}"
        lines.append("│" + cells + "│")
    lines.append("└" + "─" * (state["size"] * 6) + "┘")
    return "\n".join(lines)
