from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from autogrid.providers.alpaca import download_alpaca_bars


class AlpacaProviderTests(unittest.TestCase):
    def test_requires_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                download_alpaca_bars("unused.csv", "2025-01-01", "2025-01-02", ("A", "B"))


if __name__ == "__main__":
    unittest.main()
