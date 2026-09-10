"""Image preparation utilities for downstream document processing."""

from pathlib import Path
from typing import Union

import cv2
import numpy as np


PathLike = Union[str, Path]
MAX_IMAGE_DIMENSION = 2_000


def preprocess_image(input_path: PathLike, output_path: PathLike) -> Path:
    """Create a normalized, OCR-friendly grayscale image.

    Images larger than ``MAX_IMAGE_DIMENSION`` on either side are downscaled
    proportionally before light denoising, local contrast enhancement, and
    adaptive thresholding. The saved result is a single-channel binary image.

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
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise ValueError(f"Unable to read input image: {source}") from exc

    if image is None or image.size == 0:
        raise ValueError(f"Unable to read input image: {source}")

    height, width = image.shape[:2]
    if height == 0 or width == 0:
        raise ValueError(f"Input image has invalid dimensions: {source}")

    largest_dimension = max(height, width)
    if largest_dimension > MAX_IMAGE_DIMENSION:
        scale = MAX_IMAGE_DIMENSION / largest_dimension
        image = cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.GaussianBlur(grayscale, (3, 3), 0)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
    processed = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        written = cv2.imwrite(str(destination), processed)
    except cv2.error as exc:
        raise OSError(f"Unable to write processed image: {destination}") from exc

    if not written:
        raise OSError(f"Unable to write processed image: {destination}")

    return destination
