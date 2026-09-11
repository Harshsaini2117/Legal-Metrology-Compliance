import os
import unittest
from unittest.mock import patch

from backend.app.runtime import PADDLE_MKLDNN_ENV_VAR, configure_paddle_runtime


class PaddleRuntimeConfigurationTests(unittest.TestCase):
    def test_disables_mkldnn_for_each_backend_process(self):
        with patch.dict(os.environ, {PADDLE_MKLDNN_ENV_VAR: "1"}):
            configure_paddle_runtime()
            self.assertEqual(os.environ[PADDLE_MKLDNN_ENV_VAR], "0")


if __name__ == "__main__":
    unittest.main()
