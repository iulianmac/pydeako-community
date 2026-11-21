"""Test the public API that Home Assistant and other users import."""

import pydeako
from pydeako import deako, discover, models


def test_home_assistant_imports() -> None:
    """Test the names Home Assistant's deako integration imports."""
    for name in (
        "Deako",
        "DeakoDiscoverer",
        "DevicesNotFoundException",
        "FindDevicesError",
    ):
        assert name in pydeako.__all__
        assert hasattr(pydeako, name)


def test_exceptions_follow_pep8_names() -> None:
    """Test exception names end in Error, keeping the old name working."""
    assert issubclass(pydeako.DevicesNotFoundError, Exception)
    assert pydeako.DevicesNotFoundException is pydeako.DevicesNotFoundError
    assert discover.DevicesNotFoundError is pydeako.DevicesNotFoundError
    assert "DevicesNotFoundError" in pydeako.__all__


def test_all_names_exist() -> None:
    """Test every name in each __all__ can be imported."""
    for module in (pydeako, deako, discover, models):
        for name in module.__all__:
            assert hasattr(module, name), f"{module.__name__}.{name}"
