"""
Control Deako smart lights over the local network.

The package provides:
 - models to interact with Deako devices locally with a socket connection
 - implementation of a Deako socket client
 - mdns discovery client
"""
# pylint: disable=duplicate-code
from .deako import Deako, FindDevicesError
from .discover import (
    DeakoDiscoverer,
    DevicesNotFoundError,
    DevicesNotFoundException,
)
from .models import (
    RequestType,
    ResponseType,
    device_list_request,
    device_ping_request,
    state_change_request,
)

__all__ = [
    'Deako',
    'DeakoDiscoverer',
    'DevicesNotFoundError',
    'DevicesNotFoundException',
    'FindDevicesError',
    'RequestType',
    'ResponseType',
    'device_list_request',
    'device_ping_request',
    'state_change_request',
]
