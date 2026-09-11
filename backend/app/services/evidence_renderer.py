"""Render OCR and deterministic compliance evidence onto the source image."""

from collections.abc import Mapping, Sequence
from math import isfinite
from os import PathLike
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


_EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "data" / "evidence"
_NORMAL_COLOR = "#1677C8"
_VIOLATION_COLOR = "#C62828"


def render_evidence_image(
    image_path: str | PathLike[str],
    ocr_results: Any,
    compliance_report: Any,
    extracted_fields: Any = None,
    output_path: str | PathLike[str] | None = None,
    coordinate_image_path: str | PathLike[str] | None = None,
) -> Path:
    """Save an annotated copy of ``image_path`` and return its path.

    Blue boxes identify ordinary OCR detections. Red boxes identify detections
    whose extracted field is associated with an existing failed rule. This
    renderer only reads the supplied rule results; it does not evaluate rules.

    Raises:
        FileNotFoundError: If the source image does not exist.
        ValueError: If the source image or an OCR bounding box is invalid.
        TypeError: If OCR results are not a sequence of detection mappings.
        OSError: If the destination cannot be created or written.
    """
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"Evidence source image does not exist or is not a file: {source}")
    detections = _detections(ocr_results)
    destination = Path(output_path) if output_path is not None else _default_output_path(source)
    if destination.exists() and destination.is_dir():
        raise ValueError("Evidence output path must name a file, not a directory.")

    try:
        with Image.open(source) as opened:
            image = opened.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"Unable to open evidence source image: {source}") from exc

    coordinate_scale = _coordinate_scale(coordinate_image_path, image.size)
    failed_rules = _failed_rules_by_field(compliance_report)
    fields = extracted_fields if isinstance(extracted_fields, Mapping) else {}
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    for index, detection in enumerate(detections):
        box_value = detection.get("bounding_box")
        if box_value is None:
            continue
        box = _scale_box(_parse_box(box_value, index), coordinate_scale)
        text = detection.get("text")
        if not isinstance(text, str):
            raise ValueError(f"OCR detection {index} has non-string text.")

        related_fields = _matching_fields(text, fields)
        rule_ids = sorted({rule for field in related_fields for rule in failed_rules.get(field, set())})
        color = _VIOLATION_COLOR if rule_ids else _NORMAL_COLOR
        draw.line(box + [box[0]], fill=color, width=3, joint="curve")
        label = _label(text, rule_ids)
        if label:
            _draw_label(draw, box, label, color, image.height, font)

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG")
    except OSError as exc:
        raise OSError(f"Unable to write evidence image: {destination}") from exc
    if not destination.is_file() or destination.stat().st_size == 0:
        raise OSError(f"Evidence image was not created: {destination}")
    return destination


def _default_output_path(source: Path) -> Path:
    return _EVIDENCE_DIR / f"{source.stem}_evidence.png"


def _coordinate_scale(coordinate_image_path: str | PathLike[str] | None, output_size: tuple[int, int]) -> tuple[float, float]:
    """Map OCR coordinates from a preprocessed image back to the original."""
    if coordinate_image_path is None:
        return (1.0, 1.0)
    coordinate_image = Path(coordinate_image_path)
    if not coordinate_image.is_file():
        raise FileNotFoundError(f"OCR coordinate image does not exist or is not a file: {coordinate_image}")
    try:
        with Image.open(coordinate_image) as opened:
            coordinate_size = opened.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"Unable to open OCR coordinate image: {coordinate_image}") from exc
    if coordinate_size[0] <= 0 or coordinate_size[1] <= 0:
        raise ValueError(f"OCR coordinate image has invalid dimensions: {coordinate_image}")
    return (output_size[0] / coordinate_size[0], output_size[1] / coordinate_size[1])


def _detections(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("ocr_results must be a sequence of OCR detection mappings.")
    result = []
    for index, detection in enumerate(value):
        if not isinstance(detection, Mapping):
            raise TypeError(f"OCR detection {index} must be a mapping.")
        result.append(detection)
    return result


def _parse_box(value: Any, detection_index: int) -> list[tuple[float, float]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        raise ValueError(f"OCR detection {detection_index} has a malformed bounding_box; expected four coordinate points.")
    points: list[tuple[float, float]] = []
    for point_index, point in enumerate(value):
        if (
            not isinstance(point, Sequence)
            or isinstance(point, (str, bytes))
            or len(point) != 2
            or not all(isinstance(coordinate, (int, float)) and not isinstance(coordinate, bool) and isfinite(coordinate) for coordinate in point)
        ):
            raise ValueError(
                f"OCR detection {detection_index} has a malformed bounding_box point {point_index}; expected two finite numbers."
            )
        points.append((float(point[0]), float(point[1])))
    return points


def _scale_box(box: list[tuple[float, float]], scale: tuple[float, float]) -> list[tuple[float, float]]:
    return [(x * scale[0], y * scale[1]) for x, y in box]


def _failed_rules_by_field(compliance_report: Any) -> dict[str, set[str]]:
    if not isinstance(compliance_report, Mapping):
        return {}
    failed: dict[str, set[str]] = {}
    for check in _mapping_sequence(compliance_report.get("checks")) + _mapping_sequence(compliance_report.get("violations")):
        field = check.get("field")
        rule_id = check.get("rule_id")
        if isinstance(field, str) and field and isinstance(rule_id, str) and rule_id and check.get("status", "FAIL") == "FAIL":
            failed.setdefault(field, set()).add(rule_id)
    return failed


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _matching_fields(text: str, fields: Mapping[str, Any]) -> list[str]:
    normalized = text.casefold()
    return [
        name for name, value in fields.items()
        if isinstance(name, str) and isinstance(value, str) and value.strip() and value.casefold() in normalized
    ]


def _label(text: str, rule_ids: list[str]) -> str:
    compact_text = " ".join(text.split())
    if not compact_text:
        return "VIOLATION: " + ", ".join(rule_ids) if rule_ids else ""
    prefix = f"VIOLATION ({', '.join(rule_ids)}): " if rule_ids else "OCR: "
    return (prefix + compact_text)[:120]


def _draw_label(draw: ImageDraw.ImageDraw, box: list[tuple[float, float]], label: str, color: str, image_height: int, font: ImageFont.ImageFont) -> None:
    left = min(point[0] for point in box)
    top = min(point[1] for point in box)
    label_bounds = draw.textbbox((0, 0), label, font=font)
    label_height = label_bounds[3] - label_bounds[1] + 4
    y = top - label_height if top >= label_height else min(image_height - label_height, max(point[1] for point in box) + 2)
    draw.rectangle((left, y, left + (label_bounds[2] - label_bounds[0]) + 6, y + label_height), fill=color)
    draw.text((left + 3, y + 2), label, fill="white", font=font)
