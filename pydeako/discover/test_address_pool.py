"""Test the address pool used by discoverer."""

from uuid import uuid4

import pytest

from ._address_pool import EmptyAddressPoolError, _AddressPool


def test_init():
    """Test init."""
    pool = _AddressPool()
    assert pool is not None


def test_add():
    """Test _AddressPool.add_address."""
    pool = _AddressPool()
    address1, name1 = str(uuid4()), str(uuid4())
    pool.add_address(address1, name1)
    assert pool.available_addresses() == 1

    address, name = pool.get_address()
    assert address == address1
    assert name == name1
    # still known, so a reconnect can use it again
    assert pool.available_addresses() == 1
    assert pool.get_address() == (address1, name1)


def test_multiple_add_rotates():
    """Test _AddressPool.get_address cycles through the addresses."""
    pool = _AddressPool()
    address1, name1 = str(uuid4()), str(uuid4())
    address2, name2 = str(uuid4()), str(uuid4())
    pool.add_address(address1, name1)
    assert pool.available_addresses() == 1
    pool.add_address(address2, name2)
    assert pool.available_addresses() == 2

    # newest first, then the others in turn
    assert pool.get_address() == (address2, name2)
    assert pool.get_address() == (address1, name1)
    assert pool.get_address() == (address2, name2)
    assert pool.available_addresses() == 2


def test_add_again_is_tried_next():
    """Test re-announcing an address makes it the next one to try."""
    pool = _AddressPool()
    pool.add_address("10.0.0.1:23", "a")
    pool.add_address("10.0.0.2:23", "b")
    pool.add_address("10.0.0.1:23", "a")

    assert pool.get_address() == ("10.0.0.1:23", "a")


def test_remove_service():
    """Test _AddressPool.remove_service drops all of a service's addresses."""
    pool = _AddressPool()
    pool.add_address("10.0.0.1:23", "a")
    pool.add_address("10.0.0.3:23", "a")
    pool.add_address("10.0.0.2:23", "b")

    pool.remove_service("a")

    assert pool.available_addresses() == 1
    assert pool.get_address() == ("10.0.0.2:23", "b")
    pool.remove_service("a")  # unknown name is ignored


def test_get_empty_raises():
    """Test _AddressPool.get_address raises EmptyAddresspool when empty."""
    pool = _AddressPool()

    with pytest.raises(EmptyAddressPoolError):
        pool.get_address()


def test_removed():
    """Test _AddressPool.remove_address."""
    pool = _AddressPool()

    address, name = str(uuid4()), str(uuid4())
    pool.add_address(address, name)
    assert pool.available_addresses() == 1

    pool.remove_address(address)

    assert pool.available_addresses() == 0

    with pytest.raises(EmptyAddressPoolError):
        pool.get_address()


def test_remove_key_error_ignored():
    """Test _AddressPool.remove_address."""
    pool = _AddressPool()

    address, name = str(uuid4()), str(uuid4())
    pool.add_address(address, name)
    assert pool.available_addresses() == 1

    pool.remove_address(address)

    assert pool.available_addresses() == 0

    pool.remove_address(address)


def test_set_service_replaces_its_addresses():
    """Test _AddressPool.set_service swaps one service's addresses."""
    pool = _AddressPool()
    pool.add_address("10.0.0.1:23", "a")
    pool.add_address("10.0.0.2:23", "b")

    pool.set_service("a", ["10.0.0.9:23"])

    assert pool.available_addresses() == 2
    # the new address is tried next, the other service is untouched
    assert pool.get_address() == ("10.0.0.9:23", "a")
    assert pool.get_address() == ("10.0.0.2:23", "b")
    assert pool.get_address() == ("10.0.0.9:23", "a")
