from __future__ import annotations

import json
from collections import defaultdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from .text_utils import canonical_cable_code, normalize_code_identifier


class EntityRepository:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.entities: dict[str, dict[str, Any]] = data.get("entities", {})

    @classmethod
    def default(cls) -> "EntityRepository":
        data_path = files("projecthandler.data").joinpath("entity_definitions.json")
        with data_path.open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    @classmethod
    def from_json(cls, path: str | Path) -> "EntityRepository":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def display_name(self, entity_type: str) -> str:
        return self.entities.get(entity_type, {}).get("display_name", entity_type)

    def records(self, entity_type: str) -> list[dict[str, Any]]:
        return list(self.entities.get(entity_type, {}).get("records", []))

    def records_by_name(self, entity_type: str) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for record in self.records(entity_type):
            name = record.get("nome")
            if name is None:
                continue
            index.setdefault(normalize_code_identifier(name), record)
        return index

    def cable_records_by_code(self) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for record in self.records("cabos"):
            name = record.get("nome")
            if name is None:
                continue
            index.setdefault(canonical_cable_code(name), record)
        return index

    def pole_records_by_pair(self) -> dict[tuple[int, int], list[dict[str, Any]]]:
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for record in self.records("postes"):
            try:
                key = (int(record["altura_m"]), int(record["resistencia_dan"]))
            except (KeyError, TypeError, ValueError):
                continue
            grouped[key].append(record)
        return dict(grouped)
