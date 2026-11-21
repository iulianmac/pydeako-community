"""Address pool that is used for DeakoDiscoverer."""

import threading
from collections import OrderedDict


class EmptyAddressPoolError(Exception):
    """Empty address pool."""


class _AddressPool:
    """
    Addresses of advertised Deako devices and their mDNS service names.

    Addresses stay in the pool after use, so a reconnect can find them
    again; zeroconf only reports a service once while it stays cached.
    Zeroconf's browser thread changes the pool while the event loop reads
    it, so every access holds a lock.
    """

    # address -> service name; the next address to try is last
    addresses: OrderedDict[str, str]

    def __init__(self) -> None:
        self.addresses = OrderedDict()
        self._lock = threading.Lock()

    def available_addresses(self) -> int:
        """Return the number of available addresses."""
        with self._lock:
            return len(self.addresses)

    def add_address(self, address: str, name: str) -> None:
        """Add an address to the pool, to be tried next."""
        with self._lock:
            self.addresses[address] = name
            self.addresses.move_to_end(address)

    def get_address(self) -> tuple[str, str]:
        """Get the next address to try, then move it to the back."""
        with self._lock:
            if not self.addresses:
                raise EmptyAddressPoolError()
            address, name = next(reversed(self.addresses.items()))
            self.addresses.move_to_end(address, last=False)
            return address, name

    def remove_address(self, address: str) -> None:
        """Remove an address from the pool."""
        with self._lock:
            self.addresses.pop(address, None)

    def set_service(self, name: str, addresses: list[str]) -> None:
        """Replace a service's addresses in one step; they're tried next."""
        with self._lock:
            self._remove_service(name)
            for address in addresses:
                self.addresses[address] = name
                self.addresses.move_to_end(address)

    def remove_service(self, name: str) -> None:
        """Remove every address of a service."""
        with self._lock:
            self._remove_service(name)

    def _remove_service(self, name: str) -> None:
        """Remove a service's addresses; the caller holds the lock."""
        for address in [a for a, n in self.addresses.items() if n == name]:
            del self.addresses[address]
