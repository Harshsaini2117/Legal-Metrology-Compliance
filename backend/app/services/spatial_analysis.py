"""Small, deterministic spatial model for OCR declaration ownership.

This module deliberately works only with OCR geometry already returned by the
engine.  It does not try to segment an image or infer text that was not read.
Its regions are conservative: detections without usable boxes remain available
to legacy extraction, but are never claimed by a spatial relationship.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from collections.abc import Iterable, Mapping
from typing import Any


_CUES: dict[str, re.Pattern[str]] = {
    "title": re.compile(r"\b(?:product(?:\s+name)?|name\s+of\s+product)\b", re.I),
    "pricing": re.compile(r"\b(?:m\s*\.?r\s*\.?p\s*\.?|maximum\s+retail\s+price|inclusive\s+of|incl\.?\s+of)\b", re.I),
    "entity": re.compile(r"\b(?:manufactured|manufacturer|imported|importer|packed|packer)\b", re.I),
    "contact": re.compile(r"\b(?:consumer|customer|helpline|toll\s*free|complaints?|queries?|contact\s+us|support)\b", re.I),
    "nutrition": re.compile(r"\b(?:nutrition(?:al)?|ingredients?|energy|protein|carbohydrate|sodium|serving)\b", re.I),
    "identifier": re.compile(r"\b(?:fssai|licen[cs]e|barcode|ean|upc|gstin)\b|^\s*\d[\d\s-]{5,}\s*$", re.I),
}


@dataclass(frozen=True)
class SpatialDetection:
    """An OCR detection plus normalized geometry and semantic cues."""

    index: int
    text: str
    confidence: float | None
    bounding_box: Any
    bounds: tuple[float, float, float, float] | None
    region_id: int | None
    cues: frozenset[str]

    @property
    def center(self) -> tuple[float, float] | None:
        if self.bounds is None:
            return None
        left, top, right, bottom = self.bounds
        return ((left + right) / 2, (top + bottom) / 2)


class SpatialLayout:
    """Geometry-driven OCR groups with explicit, inspectable ownership.

    Regions are connected visual blocks.  Neighbouring lines join only when
    they overlap horizontally (or sit on the same row with a small gap), so
    unrelated columns do not become one declaration merely due to OCR order.
    """

    def __init__(self, ocr_results: Iterable[Mapping[str, Any]] | None):
        raw: list[tuple[int, str, float | None, Any, tuple[float, float, float, float] | None]] = []
        for index, item in enumerate(ocr_results or []):
            if not isinstance(item, Mapping) or not isinstance(item.get("text"), str):
                continue
            text = _normal(item["text"])
            if not text:
                continue
            confidence = item.get("confidence")
            raw.append((index, text, float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None, item.get("bounding_box"), _bounds(item.get("bounding_box"))))
        heights = [box[3] - box[1] for *_, box in raw if box and box[3] > box[1]]
        self.line_height = median(heights) if heights else 12.0
        components = _components(raw, self.line_height)
        region_by_index = {index: region for region, component in enumerate(components) for index in component}
        self.detections = tuple(
            SpatialDetection(index, text, confidence, box, bounds, region_by_index.get(index), _cues(text))
            for index, text, confidence, box, bounds in raw
        )

    @property
    def has_geometry(self) -> bool:
        return any(item.bounds is not None for item in self.detections)

    def reading_lines(self) -> list[str]:
        """Return row-aware order, retaining source order if geometry is partial."""
        if not self.detections or not all(item.bounds for item in self.detections):
            return [item.text for item in self.detections]
        rows: list[list[SpatialDetection]] = []
        for item in sorted(self.detections, key=lambda value: (value.bounds[1], value.bounds[0], value.index)):  # type: ignore[index]
            if not rows or abs(item.center[1] - rows[-1][0].center[1]) > self.line_height * 0.75:  # type: ignore[index]
                rows.append([item])
            else:
                rows[-1].append(item)
        return [item.text for row in rows for item in sorted(row, key=lambda value: (value.bounds[0], value.index))]  # type: ignore[index]

    def in_region(self, anchor: SpatialDetection) -> list[SpatialDetection]:
        if anchor.region_id is None:
            return [anchor]
        return [item for item in self.detections if item.region_id == anchor.region_id]

    def below_in_region(self, anchor: SpatialDetection) -> list[SpatialDetection]:
        """Lines below an anchor in its visual lane, nearest first."""
        if anchor.bounds is None:
            return []
        left, _, right, bottom = anchor.bounds
        result = []
        for item in self.in_region(anchor):
            if item.index == anchor.index or item.bounds is None or item.bounds[1] < bottom:
                continue
            other_left, top, other_right, _ = item.bounds
            overlap = max(0.0, min(right, other_right) - max(left, other_left))
            # A line can be wider/narrower than its label; center containment
            # safely covers this common address-panel case.
            center_in_lane = left - self.line_height <= (other_left + other_right) / 2 <= right + self.line_height
            if overlap > 0 or center_in_lane:
                result.append(item)
        return sorted(result, key=lambda value: (value.bounds[1], value.bounds[0], value.index))  # type: ignore[index]

    def related(self, first: SpatialDetection, second: SpatialDetection, *, vertical_lines: float = 4.0) -> bool:
        """Whether two detections visibly belong to the same local panel."""
        if first.bounds is None or second.bounds is None or first.region_id != second.region_id:
            return False
        a_left, a_top, a_right, a_bottom = first.bounds
        b_left, b_top, b_right, b_bottom = second.bounds
        overlap = max(0.0, min(a_right, b_right) - max(a_left, b_left))
        min_width = min(a_right - a_left, b_right - b_left)
        gap = max(0.0, b_top - a_bottom, a_top - b_bottom)
        return min_width > 0 and overlap >= min_width * 0.35 and gap <= self.line_height * vertical_lines


def _components(raw: list[tuple[int, str, float | None, Any, tuple[float, float, float, float] | None]], line_height: float) -> list[set[int]]:
    positioned = [value for value in raw if value[4] is not None]
    parent = {value[0]: value[0] for value in positioned}
    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value
    def join(a: int, b: int) -> None:
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a
    for offset, first in enumerate(positioned):
        a_left, a_top, a_right, a_bottom = first[4]  # type: ignore[misc]
        for second in positioned[offset + 1:]:
            b_left, b_top, b_right, b_bottom = second[4]  # type: ignore[misc]
            vertical_gap = max(0.0, b_top - a_bottom, a_top - b_bottom)
            overlap = max(0.0, min(a_right, b_right) - max(a_left, b_left))
            same_row = vertical_gap == 0 and abs((a_top + a_bottom) - (b_top + b_bottom)) / 2 <= line_height * 0.8
            horizontal_gap = max(0.0, b_left - a_right, a_left - b_right)
            if (overlap > 0 and vertical_gap <= line_height * 4) or (same_row and horizontal_gap <= line_height * 3):
                join(first[0], second[0])
    groups: dict[int, set[int]] = {}
    for index in parent:
        groups.setdefault(find(index), set()).add(index)
    return list(groups.values())


def _cues(text: str) -> frozenset[str]:
    return frozenset(name for name, pattern in _CUES.items() if pattern.search(text))


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def _bounds(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)):
        return None
    points = [point for point in value if isinstance(point, (list, tuple)) and len(point) >= 2 and isinstance(point[0], (int, float)) and isinstance(point[1], (int, float))]
    if not points:
        return None
    xs, ys = [float(point[0]) for point in points], [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)
