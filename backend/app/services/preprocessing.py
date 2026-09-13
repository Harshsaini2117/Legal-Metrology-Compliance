"""Image preparation utilities for downstream document processing."""

from pathlib import Path
from typing import Union

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


PathLike = Union[str, Path]
MAX_IMAGE_DIMENSION = 2_000
MIN_OCR_DIMENSION = 1_200


def preprocess_image(input_path: PathLike, output_path: PathLike) -> Path:
    """Create a normalized, OCR-friendly image while preserving text detail.

    The source is first corrected for a trusted EXIF orientation, resized
    proportionally to a useful OCR range, and given a mild LAB luminance
    normalization.  Colour channels and antialiasing are retained; aggressive
    thresholding and guessed perspective transforms are deliberately avoided
    because they can erase small declarations or distort package artwork.

    Args:
        input_path: Path to a source image readable by OpenCV.
        output_path: Destination path, including a supported image extension.

    Returns:
        The destination path after the processed image has been written.

    Raises:
        FileNotFoundError: If ``input_path`` does not point to a file.
        ValueError: If the input cannot be decoded as a valid image.
        OSError: If the output image cannot be written.
    """
    source = Path(input_path)
    destination = Path(output_path)

    if not source.is_file():
        raise FileNotFoundError(f"Input image does not exist or is not a file: {source}")

    try:
        with Image.open(source) as opened:
            oriented = ImageOps.exif_transpose(opened).convert("RGB")
            image = cv2.cvtColor(np.asarray(oriented), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, ValueError, cv2.error) as exc:
        raise ValueError(f"Unable to read input image: {source}") from exc

    if image is None or image.size == 0:
        raise ValueError(f"Unable to read input image: {source}")

    height, width = image.shape[:2]
    if height == 0 or width == 0:
        raise ValueError(f"Input image has invalid dimensions: {source}")

    largest_dimension = max(height, width)
    if largest_dimension > MAX_IMAGE_DIMENSION or largest_dimension < MIN_OCR_DIMENSION:
        target_dimension = min(MAX_IMAGE_DIMENSION, max(MIN_OCR_DIMENSION, largest_dimension))
        scale = target_dimension / largest_dimension
        image = cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )

    image = _normalize_luminance(image)

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        written = cv2.imwrite(str(destination), image)
    except cv2.error as exc:
        raise OSError(f"Unable to write processed image: {destination}") from exc

    if not written:
        raise OSError(f"Unable to write processed image: {destination}")

    return destination


def _normalize_luminance(image: np.ndarray) -> np.ndarray:
    """Improve uneven label lighting without converting colour artwork to binary."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)
    normalized_lightness = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(lightness)
    normalized = cv2.merge((normalized_lightness, a_channel, b_channel))
    return cv2.cvtColor(normalized, cv2.COLOR_LAB2BGR)
