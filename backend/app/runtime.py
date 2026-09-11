"""Runtime settings required by the local PaddleOCR backend."""

import os


PADDLE_MKLDNN_ENV_VAR = "PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"


def configure_paddle_runtime() -> None:
    """Disable oneDNN/MKLDNN before PaddleOCR is imported or initialized."""
    os.environ[PADDLE_MKLDNN_ENV_VAR] = "0"
