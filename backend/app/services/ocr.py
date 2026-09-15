"""PaddleOCR-backed text extraction utilities."""

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Union

import cv2
import numpy as np

from ..runtime import configure_paddle_runtime


PathLike = Union[str, Path]
_RETRY_MIN_DETECTIONS = 4
_RETRY_MIN_CONFIDENCE = 0.70
_DECLARATION_TERMS = ("mrp", "net", "quantity", "manufactured", "imported", "packed", "mfg", "consumer")
_SMALL_TEXT_CUE_PATTERN = re.compile(
    r"\b(?:consumer|customer|helpline|toll\s*free|complaints?|queries?|"
    r"feedback|importer(?:'s)?\s+address|manufacturer(?:'s)?\s+address|"
    r"packer(?:'s)?\s+address)\b",
    re.IGNORECASE,
)
_ENTITY_CUE_PATTERN = re.compile(
    r"\b(?:manufactured|manufacturer|imported|importer|packed|packer)\b",
    re.IGNORECASE,
)
_MIN_RETRY_DECLARATION_CONFIDENCE = 0.60


def extract_text(image_path: PathLike) -> list[dict[str, Any]]:
    """Extract text, confidence scores, and bounding boxes from an image.

    Each returned item has ``text``, ``confidence``, and ``bounding_box``
    fields. ``bounding_box`` is ``None`` only when the OCR engine does not
    provide coordinates for a detection.

    Raises:
        FileNotFoundError: If ``image_path`` does not point to a file.
        ValueError: If OpenCV cannot decode the source image.
        RuntimeError: If PaddleOCR is unavailable or cannot initialize.
    """
    source = Path(image_path)
    image = _read_image(source)
    engine = _get_ocr_engine()

    primary = _run_ocr(engine, image)
    if not _needs_retry(primary):
        if _needs_small_text_retry(primary):
            retry_image, y_offset, scale = _small_text_retry_image(image)
            return _merge_declaration_retry(
                primary,
                _restore_retry_coordinates(_run_ocr(engine, retry_image), scale, y_offset),
            )
        return primary

    retry = _run_ocr(engine, _retry_image(image))
    return retry if _result_quality(retry) > _result_quality(primary) else primary


def _run_ocr(engine: Any, image: np.ndarray) -> list[dict[str, Any]]:
    if hasattr(engine, "predict"):
        return _parse_predict_results(engine.predict(image))
    return _parse_legacy_results(engine.ocr(image, cls=True))


def _needs_retry(results: list[dict[str, Any]]) -> bool:
    if len(results) < _RETRY_MIN_DETECTIONS:
        return True
    confidences = [item["confidence"] for item in results if isinstance(item.get("confidence"), (int, float))]
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return average_confidence < _RETRY_MIN_CONFIDENCE


def _result_quality(results: list[dict[str, Any]]) -> tuple[int, float, int]:
    """Rank alternate OCR passes without combining unrelated noisy detections."""
    confidences = [float(item["confidence"]) for item in results if isinstance(item.get("confidence"), (int, float))]
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    anchors = sum(
        any(term in str(item.get("text", "")).casefold() for term in _DECLARATION_TERMS)
        for item in results
    )
    return anchors, average_confidence, len(results)


def _retry_image(image: np.ndarray) -> np.ndarray:
    """Create a mild grayscale retry view for difficult low-contrast labels."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR)


def _needs_small_text_retry(results: list[dict[str, Any]]) -> bool:
    """Request one enhanced pass only for otherwise usable labels missing care evidence."""
    texts = [str(item.get("text", "")) for item in results]
    return bool(texts) and any(_ENTITY_CUE_PATTERN.search(text) for text in texts) and not any(
        _SMALL_TEXT_CUE_PATTERN.search(text) for text in texts
    )


def _small_text_retry_image(image: np.ndarray) -> tuple[np.ndarray, int, float]:
    """Enlarge the lower declaration panel and retain its source coordinates."""
    y_offset = round(image.shape[0] * 0.55)
    panel = image[y_offset:, :]
    scale = 1.5
    enlarged = cv2.resize(panel, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
    normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR), y_offset, scale


def _restore_retry_coordinates(
    results: list[dict[str, Any]], scale: float, y_offset: int
) -> list[dict[str, Any]]:
    """Map crop-local retry boxes back to the primary image coordinate space."""
    restored: list[dict[str, Any]] = []
    for item in results:
        copied = dict(item)
        box = item.get("bounding_box")
        if isinstance(box, list):
            copied["bounding_box"] = [
                [float(point[0]) / scale, float(point[1]) / scale + y_offset]
                for point in box
                if isinstance(point, (list, tuple)) and len(point) >= 2
                and isinstance(point[0], (int, float)) and isinstance(point[1], (int, float))
            ]
        restored.append(copied)
    return restored


def _merge_declaration_retry(
    primary: list[dict[str, Any]], retry: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep original OCR and only add non-duplicate declaration evidence."""
    merged = list(primary)
    for candidate in retry:
        if _is_duplicate_detection(candidate, merged):
            continue
        if _is_meaningful_retry_detection(candidate, retry):
            merged.append(candidate)
    return merged


def _is_duplicate_detection(candidate: Mapping[str, Any], existing: list[dict[str, Any]]) -> bool:
    text = _normalized_detection_text(candidate.get("text"))
    return bool(text) and any(text == _normalized_detection_text(item.get("text")) for item in existing)


def _is_meaningful_retry_detection(candidate: Mapping[str, Any], retry: list[dict[str, Any]]) -> bool:
    text = candidate.get("text")
    confidence = candidate.get("confidence")
    if not isinstance(text, str) or not isinstance(confidence, (int, float)):
        return False
    if float(confidence) < _MIN_RETRY_DECLARATION_CONFIDENCE:
        return False
    if _SMALL_TEXT_CUE_PATTERN.search(text):
        return True
    return _is_address_fragment(text) and _nearby_entity_declaration(candidate, retry)


def _is_address_fragment(text: str) -> bool:
    return bool(re.search(r"\b(?:floor|road|street|marg|lane|estate|sector|building|court|p(?:in)?\s*[-:]?\s*\d{6})\b", text, re.IGNORECASE))


def _nearby_entity_declaration(candidate: Mapping[str, Any], retry: list[dict[str, Any]]) -> bool:
    candidate_box = _box_bounds(candidate.get("bounding_box"))
    if candidate_box is None:
        return False
    left, top, right, bottom = candidate_box
    candidate_height = max(bottom - top, 1.0)
    for item in retry:
        if item is candidate or not _ENTITY_CUE_PATTERN.search(str(item.get("text", ""))):
            continue
        box = _box_bounds(item.get("bounding_box"))
        if box is None:
            continue
        other_left, other_top, other_right, other_bottom = box
        overlap = max(0.0, min(right, other_right) - max(left, other_left))
        aligned = overlap >= min(right - left, other_right - other_left) * 0.2
        vertical_gap = max(0.0, top - other_bottom, other_top - bottom)
        if aligned and vertical_gap <= max(candidate_height, other_bottom - other_top) * 8:
            return True
    return False


def _box_bounds(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)):
        return None
    points = [
        point for point in value
        if isinstance(point, (list, tuple)) and len(point) >= 2
        and isinstance(point[0], (int, float)) and isinstance(point[1], (int, float))
    ]
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _normalized_detection_text(value: Any) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip() if isinstance(value, str) else ""


def _read_image(source: Path) -> np.ndarray:
    if not source.is_file():
        raise FileNotFoundError(f"Input image does not exist or is not a file: {source}")

    try:
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise ValueError(f"Unable to read input image: {source}") from exc

    if image is None or image.size == 0:
        raise ValueError(f"Unable to read input image: {source}")

    return image


@lru_cache(maxsize=1)
def _get_ocr_engine() -> Any:
    configure_paddle_runtime()

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR is unavailable. Install paddlepaddle and paddleocr in a "
            "Python environment supported by PaddlePaddle before using OCR."
        ) from exc

    try:
        return PaddleOCR(
    lang="en",
    text_detection_model_name="PP-OCRv5_mobile_det",
    text_recognition_model_name="PP-OCRv5_mobile_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
    except Exception as exc:
        raise RuntimeError("Unable to initialize the PaddleOCR engine.") from exc


def _parse_legacy_results(raw_results: Any) -> list[dict[str, Any]]:
    """Normalize PaddleOCR 2.x ``ocr`` output."""
    if not raw_results:
        return []

    detections = raw_results
    if isinstance(raw_results, (list, tuple)) and len(raw_results) == 1:
        detections = raw_results[0] or []

    results = []
    for detection in detections:
        if not _is_legacy_detection(detection):
            continue

        box, recognition = detection[0], detection[1]
        results.append(
            {
                "text": str(recognition[0]),
                "confidence": float(recognition[1]),
                "bounding_box": _to_json_coordinates(box),
            }
        )
    return results


def _parse_predict_results(predictions: Any) -> list[dict[str, Any]]:
    """Normalize PaddleOCR 3.x ``predict`` output."""
    results = []
    for prediction in predictions or []:
        data = _prediction_mapping(prediction)
        if data is None:
            continue

        texts = data.get("rec_texts", [])
        confidences = data.get("rec_scores", [])
        boxes = data.get("rec_polys") or data.get("rec_boxes") or []

        for index, text in enumerate(texts):
            confidence = confidences[index] if index < len(confidences) else 0.0
            box = boxes[index] if index < len(boxes) else None
            results.append(
                {
                    "text": str(text),
                    "confidence": float(confidence),
                    "bounding_box": _to_json_coordinates(box),
                }
            )
    return results


def _prediction_mapping(prediction: Any) -> Mapping[str, Any] | None:
    if isinstance(prediction, Mapping):
        return prediction
    if hasattr(prediction, "to_dict"):
        data = prediction.to_dict()
        if isinstance(data, Mapping):
            return data
    return None


def _is_legacy_detection(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and isinstance(value[1], (list, tuple))
        and len(value[1]) >= 2
    )


def _to_json_coordinates(box: Any) -> list[Any] | None:
    if box is None:
        return None
    return np.asarray(box).tolist()
