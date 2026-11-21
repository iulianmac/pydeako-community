"""
End-to-end tests against a fake Deako Connect on 127.0.0.1.

The fake speaks the local API
(https://github.com/DeakoLights/local-integrations/blob/master/API.md):
CRLF-delimited JSON, DEVICE_LIST followed by one DEVICE_FOUND per device,
CONTROL answered with "ok" (or a DEVICE_BUSY error) and then a
DEVICE_STATE_CHANGE event, and PING answered with PING.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from pydeako.deako import Deako, _deako, _manager

CRLF = b"\r\n"
WAIT_S = 5


class FakeDeakoConnect:
    """A Deako Connect bridge listening on a loopback port."""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, devices: dict[str, dict[str, Any]]) -> None:
        """Set up the bridge with its devices; call start() to listen."""
        self.devices = devices
        self.received: list[dict[str, Any]] = []
        self.raw_received = bytearray()
        self.busy_replies = 0
        self.response_delay_s = 0.0
        self.outstanding = 0
        self.max_outstanding = 0
        self.writers: list[asyncio.StreamWriter] = []
        self.connections = 0
        self.client_closed = asyncio.Event()
        self.server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        """Start listening on a free loopback port."""
        self.server = await asyncio.start_server(
            self._handle,
            "127.0.0.1",
            0,
        )
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Close all clients and the server."""
        self.drop_clients()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    @property
    def address(self) -> str:
        """Address in the host:port form discovery returns."""
        return f"127.0.0.1:{self.port}"

    async def get_address(self) -> tuple[str, str]:
        """Stand-in for DeakoDiscoverer.get_address."""
        return self.address, "fake._deako._tcp.local."

    def drop_clients(self) -> None:
        """Close every client connection, like a bridge reboot."""
        for writer in self.writers:
            writer.close()
        self.writers.clear()

    async def send_raw(self, data: bytes) -> None:
        """Send bytes as they are to every client."""
        for writer in self.writers:
            writer.write(data)
            await writer.drain()

    async def _send(
        self,
        writer: asyncio.StreamWriter,
        message: dict[str, Any],
    ) -> None:
        writer.write(json.dumps(message, ensure_ascii=False).encode() + CRLF)
        await writer.drain()

    async def _broadcast(self, message: dict[str, Any]) -> None:
        for writer in list(self.writers):
            await self._send(writer, message)

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self.connections += 1
        self.writers.append(writer)
        try:
            while True:
                line = await reader.readuntil(CRLF)
                self.raw_received += line
                request = json.loads(line)
                self.received.append(request)
                self.outstanding += 1
                self.max_outstanding = max(
                    self.max_outstanding,
                    self.outstanding,
                )
                await asyncio.sleep(self.response_delay_s)
                self.outstanding -= 1
                await self._answer(writer, request)
        except (asyncio.IncompleteReadError, ConnectionError):
            self.client_closed.set()

    async def _answer(
        self,
        writer: asyncio.StreamWriter,
        request: dict[str, Any],
    ) -> None:
        base = {
            "transactionId": request["transactionId"],
            "type": request["type"],
            "dst": request["src"],
            "src": "deako",
            "timestamp": 1,
        }
        if request["type"] == "PING":
            await self._send(writer, {**base, "status": "ok"})
        elif request["type"] == "DEVICE_LIST":
            await self._send(
                writer,
                {
                    **base,
                    "status": "ok",
                    "data": {"number_of_devices": len(self.devices)},
                },
            )
            for uuid, device in self.devices.items():
                await self._send(
                    writer,
                    {
                        "type": "DEVICE_FOUND",
                        "src": "deako",
                        "data": {"uuid": uuid, **device},
                    },
                )
        elif request["type"] == "CONTROL":
            await self._answer_control(writer, base, request)

    async def _answer_control(
        self,
        writer: asyncio.StreamWriter,
        base: dict[str, Any],
        request: dict[str, Any],
    ) -> None:
        if self.busy_replies:
            self.busy_replies -= 1
            await self._send(
                writer,
                {
                    **base,
                    "status": "error",
                    "data": {
                        "code": "DEVICE_BUSY",
                        "message": "Device is busy",
                    },
                },
            )
            return
        await self._send(writer, {**base, "status": "ok"})
        target = request["data"]["target"]
        self.devices[target]["state"].update(request["data"]["state"])
        await self._broadcast(
            {
                "type": "EVENT",
                "src": "deako",
                "data": {
                    "eventType": "DEVICE_STATE_CHANGE",
                    "target": target,
                    "state": dict(self.devices[target]["state"]),
                },
            }
        )


def _devices() -> dict[str, dict[str, Any]]:
    return {
        "uuid-1": {
            "name": "Kitchen",
            "capabilities": "power+dim",
            "state": {"power": False, "dim": 40},
        },
        "uuid-2": {
            "name": "Porch",
            "capabilities": "power",
            "state": {"power": True},
        },
        "uuid-3": {
            "name": "Hall",
            "capabilities": "power+dim",
            "state": {"power": False, "dim": 100},
        },
    }


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the library's polling intervals so tests run quickly."""
    monkeypatch.setattr(_manager, "CONNECTED_POLLING_INTERVAL_S", 0.01)
    monkeypatch.setattr(_deako, "DEVICE_LIST_POLLING_INTERVAL_S", 0.01)
    monkeypatch.setattr(_deako, "DEVICE_FOUND_POLLING_INTERVAL_S", 0.01)


@pytest_asyncio.fixture(name="bridge")
async def fixture_bridge() -> AsyncIterator[FakeDeakoConnect]:
    """Start a fake bridge with three devices."""
    fake = FakeDeakoConnect(_devices())
    await fake.start()
    yield fake
    await fake.stop()


@pytest_asyncio.fixture(name="client")
async def fixture_client(
    bridge: FakeDeakoConnect,
) -> AsyncIterator[Deako]:
    """Connect a Deako client to the fake bridge and find its devices."""
    deako = Deako(bridge.get_address, client_name="tests")
    await deako.connect()
    await deako.find_devices()
    yield deako
    await deako.disconnect()


async def _wait_for(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), WAIT_S)


@pytest.mark.asyncio
async def test_find_devices(client: Deako) -> None:
    """Test devices and their state are read from the bridge."""
    assert set(client.get_devices()) == {"uuid-1", "uuid-2", "uuid-3"}
    assert client.get_name("uuid-1") == "Kitchen"
    assert client.is_dimmable("uuid-1") is True
    assert client.is_dimmable("uuid-2") is False
    assert client.get_state("uuid-1") == {"power": False, "dim": 40}
    assert client.get_state("uuid-2") == {"power": True, "dim": None}


@pytest.mark.asyncio
async def test_messages_end_with_crlf(
    bridge: FakeDeakoConnect,
    client: Deako,
) -> None:
    """Test every message sent to the bridge is one CRLF-terminated line."""
    await client.control_device("uuid-1", True, 70)

    lines = bytes(bridge.raw_received).split(CRLF)
    assert lines[-1] == b""
    assert [json.loads(line)["type"] for line in lines[:-1]] == [
        "DEVICE_LIST",
        "CONTROL",
    ]
    assert bridge.received[-1]["src"] == "tests"


@pytest.mark.asyncio
async def test_control_device_state_comes_from_event(
    bridge: FakeDeakoConnect,
    client: Deako,
) -> None:
    """Test a control request updates the state via the bridge's event."""
    updated = asyncio.Event()
    client.set_state_callback("uuid-1", updated.set)

    await client.control_device("uuid-1", True, 70)
    await _wait_for(updated)

    assert client.get_state("uuid-1") == {"power": True, "dim": 70}
    assert bridge.devices["uuid-1"]["state"] == {"power": True, "dim": 70}


@pytest.mark.asyncio
async def test_concurrent_controls_are_sent_one_at_a_time(
    bridge: FakeDeakoConnect,
    client: Deako,
) -> None:
    """Test concurrent requests wait for the previous response."""
    bridge.response_delay_s = 0.05

    await asyncio.gather(
        *(client.control_device(uuid, True) for uuid in bridge.devices)
    )

    controls = [r for r in bridge.received if r["type"] == "CONTROL"]
    assert len(controls) == 3
    assert bridge.max_outstanding == 1
    assert all(d["state"]["power"] for d in bridge.devices.values())


@pytest.mark.asyncio
async def test_device_busy_is_retried(
    bridge: FakeDeakoConnect,
    client: Deako,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a DEVICE_BUSY answer is retried with a new transaction id."""
    monkeypatch.setattr(_manager, "BUSY_RETRY_DELAY_S", 0.01)
    bridge.busy_replies = 1
    updated = asyncio.Event()
    client.set_state_callback("uuid-3", updated.set)

    await client.control_device("uuid-3", True, 5)
    await _wait_for(updated)

    controls = [r for r in bridge.received if r["type"] == "CONTROL"]
    assert len(controls) == 2
    assert controls[0]["transactionId"] != controls[1]["transactionId"]
    assert client.get_state("uuid-3") == {"power": True, "dim": 5}


@pytest.mark.asyncio
async def test_disconnect_closes_the_connection(
    bridge: FakeDeakoConnect,
) -> None:
    """Test disconnect closes the socket so the bridge sees EOF."""
    deako = Deako(bridge.get_address)
    await deako.connect()
    await deako.find_devices()

    await deako.disconnect()

    await _wait_for(bridge.client_closed)
    assert deako.connection_manager.connection is None


@pytest.mark.asyncio
async def test_bridge_closing_the_connection_does_not_block(
    bridge: FakeDeakoConnect,
    client: Deako,
) -> None:
    """Test the event loop keeps running when the bridge closes the socket."""
    connection = client.connection_manager.connection
    assert connection is not None
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    ticker = asyncio.create_task(tick())
    bridge.drop_clients()
    for _ in range(100):
        await asyncio.sleep(0.01)
        if not connection.tasks:
            break
    ticker.cancel()

    assert ticks > 0
    assert not connection.is_connected()
    assert not connection.tasks


@pytest.mark.asyncio
async def test_reconnects_after_the_bridge_drops_the_connection(
    bridge: FakeDeakoConnect,
    client: Deako,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the client reconnects after a bridge reboot and works again."""
    monkeypatch.setattr(_manager, "PING_WORKER_WAIT_S", 0.05)
    monkeypatch.setattr(_manager, "RESPONSE_TIMEOUT_S", 0.05)
    manager = client.connection_manager
    # restart the ping worker so it uses the short interval
    manager.close()
    await client.connect()
    connections_before = bridge.connections

    bridge.drop_clients()
    for _ in range(int(WAIT_S / 0.01)):
        await asyncio.sleep(0.01)
        if (
            bridge.connections > connections_before
            and manager.connection is not None
            and manager.connection.is_connected()
        ):
            break

    assert bridge.connections > connections_before
    updated = asyncio.Event()
    client.set_state_callback("uuid-2", updated.set)
    await client.control_device("uuid-2", False)
    await _wait_for(updated)
    assert client.get_state("uuid-2") == {"power": False, "dim": None}
