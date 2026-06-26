from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .entity_repository import EntityRepository
from .models import EntityInstance, Project
from .text_utils import (
    clean_context,
    collapse_whitespace,
    compact_with_index,
    normalize_code_identifier,
    normalize_upper,
    normalize_with_index,
)


METADATA_LABELS: tuple[tuple[str, str], ...] = (
    ("Circuito", "circuito"),
    ("Dispositivo", "dispositivo"),
    ("Levantamento", "levantamento"),
    ("Projeto", "projeto"),
    ("Aprovacao", "aprovacao"),
    ("Aprovação", "aprovacao"),
    ("Cidade", "cidade"),
    ("Bairro", "bairro"),
    ("Cliente", "cliente"),
    ("Telefone", "telefone"),
    ("Servico", "servico"),
    ("Serviço", "servico"),
    ("Formato", "formato"),
    ("Impacto Ambiental", "impacto_ambiental"),
    ("DATA", "data"),
    ("Data", "data"),
    ("Escala", "escala"),
    ("NS", "ns"),
    ("FOLHA", "folha"),
    ("Folha", "folha"),
)


UNKNOWN_STRUCTURE_RE = re.compile(
    r"(?<![A-Z0-9])"
    r"(?P<code>(?:CEBS|CEM|CEN|CEJ|CMJ|BE|BS|CM|CE|SAI|SI|U|N|M|B|S)[A-Z0-9]{0,5})"
    r"(?:\.(?P<variant>\d+))?"
    r"(?:\((?P<quantity>\d+)\))?"
    r"(?![A-Z0-9-])"
)


class PdfProjectParser:
    def __init__(self, repository: EntityRepository | None = None) -> None:
        self.repository = repository or EntityRepository.default()

    def parse_file(self, path: str | Path) -> Project:
        pdf_path = Path(path)
        pages = self._read_pdf_pages(pdf_path)
        return self._parse_pages(pages, pdf_path.name, pdf_path)

    def parse_text(self, text: str, source_name: str = "Texto") -> Project:
        return self._parse_pages([text], source_name, None)

    def _parse_pages(self, pages: list[str], source_name: str, source_path: Path | None) -> Project:
        raw_text = "\n".join(pages)
        metadata = self._extract_metadata(raw_text)
        entities: list[EntityInstance] = []

        for page_number, page_text in enumerate(pages, start=1):
            entities.extend(self._extract_poles(page_text, page_number))
            entities.extend(self._extract_named_structures(page_text, "estruturas_mt", page_number))
            entities.extend(self._extract_named_structures(page_text, "estruturas_bt", page_number))
            entities.extend(self._extract_cables(page_text, page_number))
            entities.extend(self._extract_unknown_structures(page_text, page_number, entities))

        entities.sort(key=lambda item: (item.page or 0, item.span_start if item.span_start is not None else 10**9))
        return Project(name=source_name, source_path=source_path, metadata=metadata, entities=entities, raw_text=raw_text)

    def _read_pdf_pages(self, path: Path) -> list[str]:
        pages = self._read_with_pypdf(path)
        if any(page.strip() for page in pages):
            return pages
        return self._read_with_pdfplumber(path)

    def _read_with_pypdf(self, path: Path) -> list[str]:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return pages

    def _read_with_pdfplumber(self, path: Path) -> list[str]:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return pages

    def _extract_metadata(self, text: str) -> dict[str, str]:
        collapsed = collapse_whitespace(text)
        label_pattern = "|".join(re.escape(label) for label, _ in METADATA_LABELS)
        pattern = re.compile(rf"\b(?P<label>{label_pattern})\s*:", re.IGNORECASE)
        key_by_label = {normalize_upper(label): key for label, key in METADATA_LABELS}
        metadata: dict[str, str] = {}
        matches = list(pattern.finditer(collapsed))
        for index, match in enumerate(matches):
            normalized_label = normalize_upper(match.group("label"))
            key = key_by_label.get(normalized_label)
            if not key or key in metadata:
                continue
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(collapsed)
            raw_value = collapsed[match.end():next_start]
            value = self._clean_metadata_value(key, raw_value)
            if value:
                metadata[key] = value
        return metadata

    def _clean_metadata_value(self, key: str, value: str) -> str:
        value = collapse_whitespace(value).strip(" -")
        if key == "data":
            match = re.search(r"\d{2}/\d{2}/\d{4}", value)
            return match.group(0) if match else value[:40]
        if key == "ns":
            match = re.search(r"\d{6,}", value)
            return match.group(0) if match else value[:40]
        if key == "folha":
            match = re.search(r"\d+\s*/\s*\d+|\d+", value)
            return match.group(0).replace(" ", "") if match else value[:40]
        if key == "escala":
            match = re.search(r"\d+\s*:\s*\d+(?:\s*/\s*\d+)?", value)
            return match.group(0).replace(" ", "") if match else value[:40]
        value = re.split(r'\s+"?SEU DIA|\s+NOTAS:|\s+MUNIC[IÍ]PIO\b', value, maxsplit=1, flags=re.IGNORECASE)[0]
        return value[:120].strip()

    def _extract_poles(self, text: str, page_number: int) -> list[EntityInstance]:
        pole_pairs = self.repository.pole_records_by_pair()
        if not pole_pairs:
            return []
        heights = sorted({height for height, _ in pole_pairs}, reverse=True)
        strengths = sorted({strength for _, strength in pole_pairs}, reverse=True)
        height_pattern = "|".join(str(value) for value in heights)
        strength_pattern = "|".join(str(value) for value in strengths)
        pattern = re.compile(rf"(?<!\d)(?P<height>{height_pattern})\s*-\s*(?P<strength>{strength_pattern})(?!\d)")

        entities: list[EntityInstance] = []
        for match in pattern.finditer(text):
            height = int(match.group("height"))
            strength = int(match.group("strength"))
            records = pole_pairs.get((height, strength), [])
            if not records:
                continue
            possible_types = sorted({str(record.get("tipo")) for record in records if record.get("tipo")})
            attributes: dict[str, Any] = {
                "altura_m": height,
                "resistencia_dan": strength,
            }
            if len(possible_types) == 1:
                attributes["tipo"] = possible_types[0]
            elif possible_types:
                attributes["tipos_possiveis"] = ", ".join(possible_types)

            entities.append(
                EntityInstance(
                    entity_type="postes",
                    display_type=self.repository.display_name("postes"),
                    label=f"{height}-{strength}",
                    attributes=attributes,
                    page=page_number,
                    source_text=clean_context(text, match.start(), match.end()),
                    span_start=match.start(),
                    span_end=match.end(),
                )
            )
        return entities

    def _extract_named_structures(self, text: str, entity_type: str, page_number: int) -> list[EntityInstance]:
        records = self.repository.records_by_name(entity_type)
        matches = self._scan_normalized_codes(text, records)
        display_type = self.repository.display_name(entity_type)
        entities: list[EntityInstance] = []
        for match in matches:
            record = dict(match["record"])
            label = str(record.pop("nome", match["label"]))
            attributes = {key: value for key, value in record.items() if value not in (None, "")}
            if match.get("variant"):
                attributes["variante"] = match["variant"]
            entities.append(
                EntityInstance(
                    entity_type=entity_type,
                    display_type=display_type,
                    label=label,
                    attributes=attributes,
                    quantity=match.get("quantity", 1),
                    page=page_number,
                    source_text=clean_context(text, match["start"], match["end"]),
                    span_start=match["start"],
                    span_end=match["end"],
                )
            )
        return entities

    def _scan_normalized_codes(self, text: str, records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        normalized, index_map = normalize_with_index(text)
        codes = sorted(records, key=len, reverse=True)
        matches: list[dict[str, Any]] = []
        index = 0
        last_end = -1

        while index < len(normalized):
            if index != last_end and index > 0 and normalized[index - 1].isalnum():
                index += 1
                continue
            matched = False
            for code in codes:
                if not normalized.startswith(code, index):
                    continue
                end = index + len(code)
                if end < len(normalized) and normalized[end].isdigit() and code[-1].isdigit():
                    continue

                variant = None
                quantity = 1
                parsed_end = end
                if parsed_end < len(normalized) and normalized[parsed_end] == ".":
                    digit_end = parsed_end + 1
                    while digit_end < len(normalized) and normalized[digit_end].isdigit():
                        digit_end += 1
                    if digit_end > parsed_end + 1:
                        variant = normalized[parsed_end + 1:digit_end]
                        parsed_end = digit_end
                if parsed_end < len(normalized) and normalized[parsed_end] == "(":
                    digit_end = parsed_end + 1
                    while digit_end < len(normalized) and normalized[digit_end].isdigit():
                        digit_end += 1
                    if digit_end > parsed_end + 1 and digit_end < len(normalized) and normalized[digit_end] == ")":
                        quantity = int(normalized[parsed_end + 1:digit_end])
                        parsed_end = digit_end + 1

                has_suffix = variant is not None or quantity != 1
                if (
                    not has_suffix
                    and parsed_end < len(normalized)
                    and normalized[parsed_end].isalnum()
                    and not any(normalized.startswith(next_code, parsed_end) for next_code in codes)
                ):
                    continue

                original_start = index_map[index]
                original_end = index_map[parsed_end - 1] + 1
                matches.append(
                    {
                        "label": code,
                        "record": records[code],
                        "variant": variant,
                        "quantity": quantity,
                        "start": original_start,
                        "end": original_end,
                    }
                )
                index = parsed_end
                last_end = parsed_end
                matched = True
                break
            if not matched:
                index += 1
        return matches

    def _extract_cables(self, text: str, page_number: int) -> list[EntityInstance]:
        records = self.repository.cable_records_by_code()
        compact, index_map = compact_with_index(text)
        codes = sorted(records, key=len, reverse=True)
        code_set = set(codes)
        entities: list[EntityInstance] = []
        index = 0
        last_end = -1

        while index < len(compact):
            if index != last_end and not self._has_original_left_boundary(text, index_map[index]):
                index += 1
                continue
            matched = False
            for code in codes:
                if not compact.startswith(code, index):
                    continue
                if self._long_cable_crosses_boundary(text, compact, index_map, index, code, code_set):
                    continue
                end = index + len(code)
                original_start = index_map[index]
                original_end = index_map[end - 1] + 1
                record = dict(records[code])
                label = str(record.pop("nome"))
                entities.append(
                    EntityInstance(
                        entity_type="cabos",
                        display_type=self.repository.display_name("cabos"),
                        label=label,
                        attributes={key: value for key, value in record.items() if value not in (None, "")},
                        page=page_number,
                        source_text=clean_context(text, original_start, original_end),
                        span_start=original_start,
                        span_end=original_end,
                    )
                )
                index = end
                last_end = end
                matched = True
                break
            if not matched:
                index += 1
        return entities

    def _has_original_left_boundary(self, text: str, original_start: int) -> bool:
        if original_start <= 0:
            return True
        previous = normalize_upper(text[original_start - 1])
        return not previous or not previous[-1].isalnum()

    def _long_cable_crosses_boundary(
        self,
        text: str,
        compact: str,
        index_map: list[int],
        start: int,
        code: str,
        code_set: set[str],
    ) -> bool:
        for prefix_length in range(len(code) - 1, 2, -1):
            prefix = code[:prefix_length]
            if prefix not in code_set or not compact.startswith(prefix, start):
                continue
            prefix_original_end = index_map[start + prefix_length - 1] + 1
            full_original_end = index_map[start + len(code) - 1] + 1
            gap = text[prefix_original_end:full_original_end]
            if any(char.isspace() or char in "()" for char in gap[:-1]):
                return True
        return False

    def _extract_unknown_structures(
        self,
        text: str,
        page_number: int,
        known_entities: list[EntityInstance],
    ) -> list[EntityInstance]:
        normalized, index_map = normalize_with_index(text)
        known_codes = set(self.repository.records_by_name("estruturas_mt"))
        known_codes.update(self.repository.records_by_name("estruturas_bt"))
        ignored = {"S", "U", "NBI", "NS", "NO", "NAO", "SIM", "CE", "CM", "BE", "BS"}
        entities: list[EntityInstance] = []

        for match in UNKNOWN_STRUCTURE_RE.finditer(normalized):
            code = normalize_code_identifier(match.group("code"))
            quantity = int(match.group("quantity") or "1")
            if code in known_codes or code in ignored:
                continue
            if not any(char.isdigit() for char in code) and not match.group("quantity"):
                continue

            original_start = index_map[match.start()]
            original_end = index_map[match.end() - 1] + 1
            if self._overlaps_known(original_start, original_end, known_entities):
                continue

            entity_type = "estruturas_bt" if code.startswith("S") else "estruturas_mt"
            attributes: dict[str, Any] = {
                "origem": "inferido",
                "observacao": "Codigo encontrado no PDF, mas ausente no vocabulario importado da planilha.",
            }
            if match.group("variant"):
                attributes["variante"] = match.group("variant")
            entities.append(
                EntityInstance(
                    entity_type=entity_type,
                    display_type=f"{self.repository.display_name(entity_type)} (inferidas)",
                    label=code,
                    attributes=attributes,
                    quantity=quantity,
                    page=page_number,
                    confidence=0.6,
                    source_text=clean_context(text, original_start, original_end),
                    span_start=original_start,
                    span_end=original_end,
                )
            )
        return entities

    def _overlaps_known(self, start: int, end: int, known_entities: list[EntityInstance]) -> bool:
        for entity in known_entities:
            if entity.span_start is None or entity.span_end is None:
                continue
            if start < entity.span_end and end > entity.span_start:
                return True
        return False
