from __future__ import annotations

import re
import unicodedata


DASH_TRANSLATION = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
})


def normalize_with_index(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    index_map: list[int] = []
    for idx, char in enumerate(text.translate(DASH_TRANSLATION)):
        decomposed = unicodedata.normalize("NFKD", char)
        for piece in decomposed:
            if unicodedata.combining(piece):
                continue
            chars.append(piece.upper())
            index_map.append(idx)
    return "".join(chars), index_map


def normalize_upper(text: str) -> str:
    normalized, _ = normalize_with_index(text)
    return normalized


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_context(text: str, start: int, end: int, radius: int = 70) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return collapse_whitespace(text[left:right])


def normalize_code_identifier(value: object) -> str:
    text = normalize_upper(str(value))
    return re.sub(r"\s+", "", text)


def canonical_cable_code(value: object) -> str:
    text = normalize_upper(str(value))
    text = text.replace(" ", "")
    return "".join(char for char in text if char not in "()\"'“”")


def compact_with_index(text: str) -> tuple[str, list[int]]:
    normalized, index_map = normalize_with_index(text)
    chars: list[str] = []
    compact_map: list[int] = []
    ignored = set(" \t\r\n()\"'“”")
    for idx, char in enumerate(normalized):
        if char in ignored:
            continue
        chars.append(char)
        compact_map.append(index_map[idx])
    return "".join(chars), compact_map

