"""PaddleOCR-backed text extraction utilities."""

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Union

import cv2
import numpy as np


PathLike = Union[str, Path]


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

    if hasattr(engine, "predict"):
        return _parse_predict_results(engine.predict(image))

    return _parse_legacy_results(engine.ocr(image, cls=True))


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
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR is unavailable. Install paddlepaddle and paddleocr in a "
            "Python environment supported by PaddlePaddle before using OCR."
        ) from exc

    try:
        return PaddleOCR(lang="en", use_angle_cls=True)
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
