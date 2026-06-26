from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
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
    ("Aprovagao", "aprovacao"),
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
    ("Scala", "escala"),
    ("COORD", "coord"),
    ("Coord", "coord"),
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

COORDINATE_LOOKAHEAD_CHARS = 120
COORDINATE_RE = re.compile(
    r"(?<!\d)(?P<x>\d{6,7})\s*(?::|/|\s)\s*(?P<y>\d{7})(?!\d)"
)
LAYOUT_COORDINATE_X_TOLERANCE = 36
LAYOUT_COORDINATE_MAX_VERTICAL_GAP = 36
LAYOUT_CONTEXT_X_TOLERANCE = 70
LAYOUT_CONTEXT_Y_TOLERANCE = 42
LAYOUT_STACK_X_TOLERANCE = 36
LAYOUT_STACK_ABOVE = 20
LAYOUT_STACK_BELOW = 28
LAYOUT_GRAPHIC_MARKER_RADIUS = 75
LAYOUT_SPAN_OFFSET = 1_000_000_000
OCR_RENDER_DPI = 300
OCR_TEXT_LENGTH_THRESHOLD = 800
OCR_WORD_COUNT_THRESHOLD = 80
OCR_TIMEOUT_SECONDS = 60


class PdfProjectParser:
    def __init__(self, repository: EntityRepository | None = None) -> None:
        self.repository = repository or EntityRepository.default()

    def parse_file(self, path: str | Path) -> Project:
        pdf_path = Path(path)
        pages = self._read_pdf_pages(pdf_path)
        try:
            page_layouts = self._read_pdf_page_layouts(pdf_path)
        except Exception:
            page_layouts = None
        if self._should_run_ocr(pages, page_layouts):
            ocr_pages, ocr_layouts = self._read_ocr_pages(pdf_path)
            if ocr_pages:
                pages = self._merge_page_texts(pages, ocr_pages)
            if ocr_layouts:
                page_layouts = ocr_layouts
        return self._parse_pages(pages, pdf_path.name, pdf_path, page_layouts)

    def parse_text(self, text: str, source_name: str = "Texto") -> Project:
        return self._parse_pages([text], source_name, None)

    def _parse_pages(
        self,
        pages: list[str],
        source_name: str,
        source_path: Path | None,
        page_layouts: list[dict[str, Any]] | None = None,
    ) -> Project:
        raw_text = "\n".join(pages)
        metadata = self._extract_metadata(raw_text)
        entities: list[EntityInstance] = []

        for page_number, page_text in enumerate(pages, start=1):
            layout = page_layouts[page_number - 1] if page_layouts and page_number <= len(page_layouts) else None
            layout_poles = self._extract_poles_from_layout(layout, page_text, page_number) if layout else []
            entities.extend(layout_poles or self._extract_poles(page_text, page_number))
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

    def _read_pdf_page_layouts(self, path: Path) -> list[dict[str, Any]]:
        import pdfplumber

        layouts: list[dict[str, Any]] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                words = page.extract_words(
                    x_tolerance=2,
                    y_tolerance=2,
                    keep_blank_chars=False,
                    use_text_flow=False,
                )
                layouts.append(
                    {
                        "words": words,
                        "objects": self._extract_layout_objects(page),
                    }
                )
        return layouts

    def _should_run_ocr(self, pages: list[str], page_layouts: list[dict[str, Any]] | None) -> bool:
        text_length = sum(len(page.strip()) for page in pages)
        word_count = 0
        if page_layouts:
            word_count = sum(len(layout.get("words", [])) for layout in page_layouts)
        return text_length < OCR_TEXT_LENGTH_THRESHOLD or word_count < OCR_WORD_COUNT_THRESHOLD

    def _read_ocr_pages(self, path: Path) -> tuple[list[str], list[dict[str, Any]]]:
        if not shutil.which("tesseract"):
            return [], []

        try:
            import fitz
        except ImportError:
            return [], []

        pages: list[str] = []
        layouts: list[dict[str, Any]] = []
        zoom = OCR_RENDER_DPI / 72

        try:
            document = fitz.open(str(path))
        except Exception:
            return [], []

        with tempfile.TemporaryDirectory(prefix="projecthandler_ocr_") as temp_dir:
            temp_path = Path(temp_dir)
            for page_index, page in enumerate(document):
                matrix = fitz.Matrix(zoom, zoom)
                page_image = temp_path / f"page_{page_index}.png"
                page.get_pixmap(matrix=matrix, alpha=False).save(page_image)

                words, ocr_text = self._read_tesseract_words(page_image, psm=11)
                text_parts = [ocr_text]
                for band_index, band_rect in enumerate(self._ocr_band_rects(page)):
                    band_image = temp_path / f"page_{page_index}_band_{band_index}.png"
                    try:
                        page.get_pixmap(matrix=matrix, clip=band_rect, alpha=False).save(band_image)
                    except Exception:
                        continue
                    band_words, band_text = self._read_tesseract_words(band_image, psm=11)
                    words.extend(self._offset_ocr_words(band_words, band_rect.x0 * zoom, band_rect.y0 * zoom))
                    text_parts.append(band_text)

                footer_text = self._read_ocr_footer_text(page, matrix, temp_path, page_index)
                text_parts.append(footer_text)
                pages.append(collapse_whitespace("\n".join(text_parts)))
                layouts.append({"words": words, "objects": []})

        document.close()
        return pages, layouts

    def _ocr_band_rects(self, page: Any) -> list[Any]:
        rect_cls = page.rect.__class__
        width = page.rect.width
        height = page.rect.height
        return [
            rect_cls(0, 0, width * 0.45, height),
            rect_cls(width * 0.20, 0, width * 0.70, height),
            rect_cls(width * 0.55, 0, width, height),
        ]

    def _offset_ocr_words(self, words: list[dict[str, Any]], x_offset: float, y_offset: float) -> list[dict[str, Any]]:
        offset_words: list[dict[str, Any]] = []
        for word in words:
            shifted = dict(word)
            shifted["x0"] = float(word.get("x0", 0)) + x_offset
            shifted["x1"] = float(word.get("x1", 0)) + x_offset
            shifted["top"] = float(word.get("top", 0)) + y_offset
            shifted["bottom"] = float(word.get("bottom", 0)) + y_offset
            offset_words.append(shifted)
        return offset_words

    def _read_ocr_footer_text(self, page: Any, matrix: Any, temp_path: Path, page_index: int) -> str:
        footer_top = page.rect.height * 0.86
        footer_rect = page.rect.__class__(0, footer_top, page.rect.width, page.rect.height)
        footer_image = temp_path / f"page_{page_index}_footer.png"
        try:
            page.get_pixmap(matrix=matrix, clip=footer_rect, alpha=False).save(footer_image)
        except Exception:
            return ""
        return self._read_tesseract_text(footer_image, psm=6)

    def _read_tesseract_words(self, image_path: Path, psm: int) -> tuple[list[dict[str, Any]], str]:
        command = ["tesseract", str(image_path), "stdout", "--psm", str(psm), "tsv"]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=OCR_TIMEOUT_SECONDS,
                check=False,
            )
        except Exception:
            return [], ""

        words: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for row in csv.DictReader(result.stdout.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            try:
                confidence = float(row.get("conf") or -1)
                left = float(row.get("left") or 0)
                top = float(row.get("top") or 0)
                width = float(row.get("width") or 0)
                height = float(row.get("height") or 0)
            except ValueError:
                continue
            if confidence < 0 or width <= 0 or height <= 0:
                continue
            words.append(
                {
                    "text": text,
                    "x0": left,
                    "x1": left + width,
                    "top": top,
                    "bottom": top + height,
                    "confidence": confidence,
                }
            )
            text_parts.append(text)

        return words, " ".join(text_parts)

    def _read_tesseract_text(self, image_path: Path, psm: int) -> str:
        command = ["tesseract", str(image_path), "stdout", "--psm", str(psm)]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=OCR_TIMEOUT_SECONDS,
                check=False,
            )
        except Exception:
            return ""
        return result.stdout

    def _merge_page_texts(self, primary_pages: list[str], extra_pages: list[str]) -> list[str]:
        page_count = max(len(primary_pages), len(extra_pages))
        merged: list[str] = []
        for index in range(page_count):
            primary = primary_pages[index] if index < len(primary_pages) else ""
            extra = extra_pages[index] if index < len(extra_pages) else ""
            merged.append(collapse_whitespace(f"{primary}\n{extra}"))
        return merged

    def _extract_layout_objects(self, page: Any) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []
        for kind in ("rects", "curves", "lines"):
            for raw_object in getattr(page, kind, []):
                x0 = min(raw_object.get("x0", 0), raw_object.get("x1", 0))
                x1 = max(raw_object.get("x0", 0), raw_object.get("x1", 0))
                top = raw_object.get("top")
                bottom = raw_object.get("bottom")
                if top is None or bottom is None:
                    y0 = raw_object.get("y0", 0)
                    y1 = raw_object.get("y1", 0)
                    top = page.height - max(y0, y1)
                    bottom = page.height - min(y0, y1)

                width = x1 - x0
                height = bottom - top
                if width > page.width * 0.75 or height > page.height * 0.75:
                    continue
                objects.append(
                    {
                        "kind": kind[:-1],
                        "x0": x0,
                        "x1": x1,
                        "top": top,
                        "bottom": bottom,
                    }
                )
        return objects

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
        value = re.sub(r"\s+\bEs\s*:?\s*$", "", value, flags=re.IGNORECASE)
        return value[:120].strip(" _|,")

    def _build_pole_pattern(self) -> tuple[dict[tuple[int, int], list[dict[str, Any]]], re.Pattern[str] | None]:
        pole_pairs = self.repository.pole_records_by_pair()
        if not pole_pairs:
            return {}, None
        heights = sorted({height for height, _ in pole_pairs}, reverse=True)
        strengths = sorted({strength for _, strength in pole_pairs}, reverse=True)
        height_pattern = "|".join(str(value) for value in heights)
        strength_pattern = "|".join(str(value) for value in strengths)
        pattern = re.compile(rf"(?<!\d)(?P<height>{height_pattern})\s*-\s*(?P<strength>{strength_pattern})(?!\d)")
        return pole_pairs, pattern

    def _extract_poles(self, text: str, page_number: int) -> list[EntityInstance]:
        pole_pairs, pattern = self._build_pole_pattern()
        if not pole_pairs or pattern is None:
            return []

        entities: list[EntityInstance] = []
        pole_matches = list(pattern.finditer(text))
        for index, match in enumerate(pole_matches):
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

            next_pole_start = (
                pole_matches[index + 1].start()
                if index + 1 < len(pole_matches)
                else len(text)
            )
            coordinate_end_limit = min(match.end() + COORDINATE_LOOKAHEAD_CHARS, next_pole_start)
            coordinate = self._extract_coordinate_after_pole(text, match.end(), coordinate_end_limit)
            span_end = match.end()
            if coordinate:
                attributes["coordenada"] = coordinate[0]
                span_end = coordinate[1]

            entities.append(
                EntityInstance(
                    entity_type="postes",
                    display_type=self.repository.display_name("postes"),
                    label=f"{height}-{strength}",
                    attributes=attributes,
                    page=page_number,
                    source_text=clean_context(text, match.start(), span_end),
                    span_start=match.start(),
                    span_end=span_end,
                )
            )
        return entities

    def _extract_coordinate_after_pole(self, text: str, start: int, end: int) -> tuple[str, int] | None:
        coordinate_match = COORDINATE_RE.search(text[start:end])
        if not coordinate_match:
            return None
        x = coordinate_match.group("x")
        y = coordinate_match.group("y")
        return f"{x} / {y}", start + coordinate_match.end()

    def _extract_poles_from_layout(
        self,
        layout: dict[str, Any],
        page_text: str,
        page_number: int,
    ) -> list[EntityInstance]:
        pole_pairs, pattern = self._build_pole_pattern()
        if not pole_pairs or pattern is None:
            return []

        words = layout.get("words", [])
        objects = layout.get("objects", [])
        coordinates = self._layout_coordinate_candidates(words)
        is_ocr_layout = any("confidence" in word for word in words[:20])
        used_coordinates: set[int] = set()
        seen_poles: set[tuple[str, str]] = set()
        entities: list[EntityInstance] = []

        for word in sorted(words, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0)))):
            pole_pair = self._parse_layout_pole_pair(self._layout_word_text(word), pole_pairs, pattern)
            if not pole_pair:
                continue

            height, strength = pole_pair
            records = pole_pairs.get((height, strength), [])
            if not records:
                continue

            coordinate_index, coordinate = self._nearest_layout_coordinate(word, coordinates, used_coordinates)
            if is_ocr_layout and coordinate is None:
                continue
            has_context = (
                coordinate is not None
                or self._has_nearby_structure_label(word, words)
                or self._has_nearby_graphic_marker(word, objects)
            )
            if not has_context:
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
            if coordinate:
                attributes["coordenada"] = coordinate["label"]
                used_coordinates.add(coordinate_index)

            entity_label = f"{height}-{strength}"
            dedupe_key = (
                entity_label,
                str(attributes.get("coordenada") or f"{round(self._layout_center_x(word) / 20)}:{round(self._layout_center_y(word) / 20)}"),
            )
            if dedupe_key in seen_poles:
                continue
            seen_poles.add(dedupe_key)

            entities.append(
                EntityInstance(
                    entity_type="postes",
                    display_type=self.repository.display_name("postes"),
                    label=entity_label,
                    attributes=attributes,
                    page=page_number,
                    source_text=self._layout_context(words, word, coordinate),
                    span_start=self._layout_span_start(page_number, word),
                    span_end=self._layout_span_end(page_number, word, coordinate),
                )
            )
        return entities

    def _parse_layout_pole_pair(
        self,
        text: str,
        pole_pairs: dict[tuple[int, int], list[dict[str, Any]]],
        pattern: re.Pattern[str],
    ) -> tuple[int, int] | None:
        exact = pattern.fullmatch(text)
        if exact:
            return int(exact.group("height")), int(exact.group("strength"))

        cleaned = self._clean_ocr_technical_text(text)
        match = re.search(r"(?P<height>\d{1,2})-(?P<strength>\d{2,4})", cleaned)
        if not match:
            return None

        raw_height = int(match.group("height"))
        raw_strength = int(match.group("strength"))
        candidate_strengths = sorted({strength for _, strength in pole_pairs})
        raw_strengths = [raw_strength]
        if raw_strength < 100:
            raw_strengths.append(raw_strength * 10)

        strength = None
        for candidate_raw_strength in raw_strengths:
            strength = self._nearest_known_value(candidate_raw_strength, candidate_strengths, tolerance=10)
            if strength is not None:
                break
        if strength is None:
            return None

        candidate_heights = sorted({height for height, known_strength in pole_pairs if known_strength == strength})
        candidate_raw_heights = [raw_height]
        if raw_height == 1:
            candidate_raw_heights.append(11)
        if raw_height == 14:
            candidate_raw_heights.append(11)

        for candidate in candidate_raw_heights:
            if candidate in candidate_heights:
                return candidate, strength
        return None

    def _nearest_known_value(self, value: int, candidates: list[int], tolerance: int) -> int | None:
        if not candidates:
            return None
        nearest = min(candidates, key=lambda candidate: abs(candidate - value))
        return nearest if abs(nearest - value) <= tolerance else None

    def _clean_ocr_technical_text(self, text: str) -> str:
        replacements = str.maketrans(
            {
                "I": "1",
                "L": "1",
                "|": "1",
                "!": "1",
                "O": "0",
                "Q": "0",
                "%": "0",
            }
        )
        normalized = normalize_upper(text).translate(replacements)
        normalized = normalized.replace("–", "-").replace("—", "-")
        return "".join(char for char in normalized if char.isdigit() or char == "-")

    def _layout_coordinate_candidates(self, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        sorted_words = sorted(words, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0))))

        for word in sorted_words:
            coordinate = self._parse_coordinate_label(self._layout_word_text(word))
            if coordinate:
                candidates.append(self._layout_coordinate_candidate(coordinate[0], coordinate[1], word, word))

        for index, first in enumerate(sorted_words):
            x = self._layout_word_text(first)
            if not re.fullmatch(r"\d{6,7}", x):
                continue
            for second in sorted_words[index + 1:]:
                y = self._layout_word_text(second)
                if not re.fullmatch(r"\d{7}", y):
                    continue
                vertical_gap = float(second.get("top", 0)) - float(first.get("bottom", 0))
                if vertical_gap < -2:
                    continue
                if vertical_gap > 20:
                    break
                if abs(self._layout_center_x(first) - self._layout_center_x(second)) <= 18:
                    candidates.append(self._layout_coordinate_candidate(x, y, first, second))
                    break

        for index, first in enumerate(sorted_words):
            first_text = self._layout_word_text(first)
            if ":" not in first_text and "/" not in first_text:
                continue
            for second in sorted_words[index + 1:index + 4]:
                if abs(self._layout_center_x(first) - self._layout_center_x(second)) > 40:
                    continue
                vertical_gap = float(second.get("top", 0)) - float(first.get("bottom", 0))
                if vertical_gap < -4 or vertical_gap > 24:
                    continue
                coordinate = self._parse_coordinate_label(first_text + self._layout_word_text(second))
                if coordinate:
                    candidates.append(self._layout_coordinate_candidate(coordinate[0], coordinate[1], first, second))
                    break

        return candidates

    def _parse_coordinate_label(self, text: str) -> tuple[str, str] | None:
        cleaned = self._clean_ocr_coordinate_text(text)
        match = re.search(r"(?P<x>\d{6,7})\D+(?P<y>\d{7})", cleaned)
        if not match:
            return None
        return match.group("x"), match.group("y")

    def _clean_ocr_coordinate_text(self, text: str) -> str:
        replacements = str.maketrans(
            {
                "I": "1",
                "L": "1",
                "|": "1",
                "!": "1",
                "O": "0",
                "Q": "0",
                "}": "",
                "{": "",
                "]": "",
                "[": "",
            }
        )
        normalized = normalize_upper(text).translate(replacements)
        return "".join(char for char in normalized if char.isdigit() or char in ":/,")

    def _layout_coordinate_candidate(
        self,
        x: str,
        y: str,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "label": f"{x} / {y}",
            "x0": min(float(first.get("x0", 0)), float(second.get("x0", 0))),
            "x1": max(float(first.get("x1", 0)), float(second.get("x1", 0))),
            "top": min(float(first.get("top", 0)), float(second.get("top", 0))),
            "bottom": max(float(first.get("bottom", 0)), float(second.get("bottom", 0))),
        }

    def _nearest_layout_coordinate(
        self,
        pole_word: dict[str, Any],
        coordinates: list[dict[str, Any]],
        used_coordinates: set[int],
    ) -> tuple[int, dict[str, Any] | None]:
        pole_center_x = self._layout_center_x(pole_word)
        pole_bottom = float(pole_word.get("bottom", 0))
        best_index = -1
        best_score: float | None = None
        best_coordinate: dict[str, Any] | None = None

        for index, coordinate in enumerate(coordinates):
            if index in used_coordinates:
                continue
            coordinate_center_x = (float(coordinate["x0"]) + float(coordinate["x1"])) / 2
            horizontal_gap = abs(coordinate_center_x - pole_center_x)
            vertical_gap = float(coordinate["top"]) - pole_bottom
            if horizontal_gap > LAYOUT_COORDINATE_X_TOLERANCE:
                continue
            if vertical_gap < -2 or vertical_gap > LAYOUT_COORDINATE_MAX_VERTICAL_GAP:
                continue
            score = vertical_gap + horizontal_gap * 0.4
            if best_score is None or score < best_score:
                best_index = index
                best_score = score
                best_coordinate = coordinate

        return best_index, best_coordinate

    def _has_nearby_structure_label(self, pole_word: dict[str, Any], words: list[dict[str, Any]]) -> bool:
        known_codes = set(self.repository.records_by_name("estruturas_mt"))
        known_codes.update(self.repository.records_by_name("estruturas_bt"))
        pole_center_x = self._layout_center_x(pole_word)
        pole_top = float(pole_word.get("top", 0))

        for word in words:
            if word is pole_word:
                continue
            word_center_x = self._layout_center_x(word)
            word_bottom = float(word.get("bottom", 0))
            if word_bottom > pole_top + 2:
                continue
            if pole_top - word_bottom > LAYOUT_CONTEXT_Y_TOLERANCE:
                continue
            if abs(word_center_x - pole_center_x) > LAYOUT_CONTEXT_X_TOLERANCE:
                continue
            normalized = normalize_code_identifier(self._layout_word_text(word))
            if any(code in normalized for code in known_codes):
                return True
        return False

    def _has_nearby_graphic_marker(self, pole_word: dict[str, Any], objects: list[dict[str, Any]]) -> bool:
        pole_center_x = self._layout_center_x(pole_word)
        pole_center_y = self._layout_center_y(pole_word)
        for obj in objects:
            width = float(obj.get("x1", 0)) - float(obj.get("x0", 0))
            height = float(obj.get("bottom", 0)) - float(obj.get("top", 0))
            if width > 70 or height > 70:
                continue
            object_center_x = (float(obj.get("x0", 0)) + float(obj.get("x1", 0))) / 2
            object_center_y = (float(obj.get("top", 0)) + float(obj.get("bottom", 0))) / 2
            distance = ((object_center_x - pole_center_x) ** 2 + (object_center_y - pole_center_y) ** 2) ** 0.5
            if distance <= LAYOUT_GRAPHIC_MARKER_RADIUS:
                return True
        return False

    def _layout_context(
        self,
        words: list[dict[str, Any]],
        pole_word: dict[str, Any],
        coordinate: dict[str, Any] | None,
    ) -> str:
        pole_center_x = self._layout_center_x(pole_word)
        top = float(pole_word.get("top", 0)) - LAYOUT_STACK_ABOVE
        bottom = float(pole_word.get("bottom", 0)) + LAYOUT_STACK_BELOW
        if coordinate:
            bottom = max(bottom, float(coordinate["bottom"]) + 0.5)

        context_words = [
            word
            for word in words
            if abs(self._layout_center_x(word) - pole_center_x) <= LAYOUT_STACK_X_TOLERANCE
            and top <= self._layout_center_y(word) <= bottom
            and len(self._layout_word_text(word)) > 1
        ]
        return collapse_whitespace(
            " ".join(
                self._layout_word_text(word)
                for word in sorted(context_words, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0))))
            )
        )

    def _layout_span_start(self, page_number: int, word: dict[str, Any]) -> int:
        return LAYOUT_SPAN_OFFSET + page_number * 10_000_000 + int(float(word.get("top", 0)) * 1000 + float(word.get("x0", 0)))

    def _layout_span_end(
        self,
        page_number: int,
        word: dict[str, Any],
        coordinate: dict[str, Any] | None,
    ) -> int:
        bottom = float(coordinate["bottom"]) if coordinate else float(word.get("bottom", 0))
        return LAYOUT_SPAN_OFFSET + page_number * 10_000_000 + int(bottom * 1000 + float(word.get("x1", 0)))

    def _layout_word_text(self, word: dict[str, Any]) -> str:
        return normalize_upper(str(word.get("text", ""))).replace(" ", "")

    def _layout_center_x(self, word: dict[str, Any]) -> float:
        return (float(word.get("x0", 0)) + float(word.get("x1", 0))) / 2

    def _layout_center_y(self, word: dict[str, Any]) -> float:
        return (float(word.get("top", 0)) + float(word.get("bottom", 0))) / 2

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
