import asyncio
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager
from board_hardware import settings


def test_handle_webapp_connected_threshold_sequence():
    async def _run_test():
        bsm = BoardStateManager()
        mock_calibrate = MagicMock(return_value=True)
        bsm._safe_calibrate = mock_calibrate  # type: ignore[assignment]

        # Set initial test thresholds
        settings["threshold_positive"] = 150
        settings["threshold_negative"] = 120

        # Run handle_webapp_connected
        await bsm.handle_webapp_connected()

        # Verify _safe_calibrate was called
        mock_calibrate.assert_called_once()

        # Verify thresholds were restored back to initial values after run
        assert settings["threshold_positive"] == 150
        assert settings["threshold_negative"] == 120

    asyncio.run(_run_test())
