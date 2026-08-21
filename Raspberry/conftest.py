"""
conftest.py - Global pytest configuration and test harness isolation.

Strictly protects the physical board configuration file (board_settings.json)
from being overwritten or modified during test execution by sandboxing
BOARD_SETTINGS_PATH in a temporary directory for all test runs.
"""

import copy
import os
import tempfile
import pytest


@pytest.fixture(autouse=True, scope="session")
def isolate_board_settings_file_globally():
    """
    Redirects BOARD_SETTINGS_PATH to an isolated temporary file for the entire test session.
    Guarantees that no test run can EVER touch or overwrite the real board_settings.json.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_settings_file = os.path.join(tmpdir, "board_settings_test.json")
        old_env = os.environ.get("BOARD_SETTINGS_PATH")
        os.environ["BOARD_SETTINGS_PATH"] = temp_settings_file
        try:
            yield temp_settings_file
        finally:
            if old_env is not None:
                os.environ["BOARD_SETTINGS_PATH"] = old_env
            else:
                os.environ.pop("BOARD_SETTINGS_PATH", None)


@pytest.fixture(autouse=True)
def isolate_board_settings_dict_per_test():
    """
    Snapshots the global board_hardware.settings dictionary before each test
    and cleanly restores factory defaults or snapshot state after each test.
    """
    try:
        from board_hardware import get_default_settings, settings
        # Start each test with clean default settings
        clean_defaults = get_default_settings()
        settings.clear()
        settings.update(clean_defaults)
        saved_settings = copy.deepcopy(clean_defaults)
    except ImportError:
        saved_settings = None

    yield

    if saved_settings is not None:
        try:
            from board_hardware import settings
            settings.clear()
            settings.update(saved_settings)
        except ImportError:
            pass
