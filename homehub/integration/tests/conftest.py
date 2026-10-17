"""Run the integration as custom_components/homehub against Home Assistant's test harness."""
import os
import sys
import tempfile

import pytest

# Home Assistant loads custom integrations from a top-level custom_components package
_ROOT = tempfile.mkdtemp(prefix="homehub-ha-")
os.makedirs(os.path.join(_ROOT, "custom_components"))
os.symlink(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "homehub")),
    os.path.join(_ROOT, "custom_components", "homehub"),
)
sys.path.insert(0, _ROOT)
# Import it now, before the test harness can put another custom_components package first
import custom_components.homehub  # noqa: E402,F401


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
