from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EntityInstance:
    entity_type: str
    display_type: str
    label: str
    attributes: dict[str, Any] = field(default_factory=dict)
    quantity: int = 1
    page: int | None = None
    confidence: float = 1.0
    source_text: str = ""
    span_start: int | None = None
    span_end: int | None = None

    def attribute_summary(self) -> str:
        parts: list[str] = []
        for key, value in self.attributes.items():
            if value in (None, ""):
                continue
            label = key.replace("_", " ")
            parts.append(f"{label}: {value}")
        return "; ".join(parts)


@dataclass(slots=True)
class Project:
    name: str
    source_path: Path | None
    metadata: dict[str, str]
    entities: list[EntityInstance]
    raw_text: str = ""

    def entity_counts(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for entity in self.entities:
            counts[entity.display_type] += max(entity.quantity, 1)
        return counts

    def grouped_entities(self) -> dict[str, list[EntityInstance]]:
        grouped: dict[str, list[EntityInstance]] = defaultdict(list)
        for entity in self.entities:
            grouped[entity.display_type].append(entity)
        return dict(grouped)

    @property
    def display_name(self) -> str:
        ns = self.metadata.get("ns")
        cidade = self.metadata.get("cidade")
        if ns and cidade:
            return f"{ns} - {cidade}"
        if ns:
            return ns
        return self.name

