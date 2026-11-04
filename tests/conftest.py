# tests/conftest.py
import pytest

try:
    import pytest_homeassistant_custom_component  # noqa: F401

    pytest_plugins = "pytest_homeassistant_custom_component"

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        yield
except ImportError:

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations():
        yield
