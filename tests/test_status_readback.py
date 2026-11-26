"""Reading the amp back: routing, volume and mute from GET frames.

The amp answers "0g<seq> c4.amp.ain|avol|amut" with one hex byte per zone
(checked on two C4-16AMP3-B, firmware 03.26.52):

    0r4e03 000 c4.amp.ain 01 02 03 04 05 06 08 08     input per zone, 00 = off
    0r8d72 000 c4.amp.avol cd cd cd e1 cd cd cd cd    percent + 155
    0r2bea 000 c4.amp.amut 00 00 00 00 00 00 00 00    1 = muted

No real sockets (the HA test plugin disables them): manager.py's `socket` is
replaced with a fake amp that answers GETs from its own state. Only the stdlib
and pytest are needed. Set C4_MANAGER_PATH to run against another manager.py.
"""
import asyncio
import importlib.util
import os
import socket
import types
from pathlib import Path

import pytest

DEFAULT_MANAGER = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "control4_mediaplayer" / "manager.py"
)


def _load():
    path = Path(os.environ.get("C4_MANAGER_PATH", DEFAULT_MANAGER))
    spec = importlib.util.spec_from_file_location("c4_manager_readback", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load()


class FakeAmp:
    def __init__(self):
        self.state = {"ain": [1, 2, 3, 4, 5, 6, 8, 8], "avol": [0xCD] * 8, "amut": [0] * 8}
        self.asked = []
        self.silent = False

    def socket_module(self):
        amp = self

        class FakeSocket:
            def __init__(self, *a):
                self._reply = None

            def settimeout(self, t):
                pass

            def sendto(self, data, addr):
                head, _, cmd = data.decode().strip().partition(" ")
                amp.asked.append(cmd)
                key = cmd.rsplit(".", 1)[-1]
                if amp.silent or not head.startswith("0g") or key not in amp.state:
                    self._reply = None
                    return
                body = " ".join(f"{v:02x}" for v in amp.state[key])
                self._reply = f"0r{head[2:]} 000 {cmd} {body}\r\n".encode()

            def recvfrom(self, n):
                if self._reply is None:
                    raise TimeoutError("timed out")
                r, self._reply = self._reply, None
                return r, ("amp", 8750)

            def close(self):
                pass

        return types.SimpleNamespace(socket=FakeSocket, AF_INET=socket.AF_INET, SOCK_DGRAM=socket.SOCK_DGRAM)


@pytest.fixture
def amp(monkeypatch):
    a = FakeAmp()
    monkeypatch.setattr(M, "socket", a.socket_module())
    M._STATUS_CACHE.clear()
    M._STATUS_LOCKS.clear()
    return a


def test_parse_list_reply():
    assert M.parse_list_reply("0r4e03 000 c4.amp.ain 01 02 03 04 05 06 08 08", "c4.amp.ain") == [1, 2, 3, 4, 5, 6, 8, 8]
    assert M.parse_list_reply("0r8b4f n01", "c4.amp.psave") is None
    assert M.parse_list_reply(None, "c4.amp.ain") is None


def test_zone_state():
    st = {"ain": [0, 2, 8], "avol": [0xCD, 0xE1, 0x9B], "amut": [0, 1, 0]}
    assert M.zone_state(st, 1, ["A", "B"])["on"] is False
    assert M.zone_state(st, 2, ["A", "B"]) == {"on": True, "source_index": 2, "source": "B", "volume": 0.7, "muted": True}
    third = M.zone_state(st, 3, ["A", "B"])
    assert third["on"] and third["source"] is None and third["volume"] == 0.0
    assert M.zone_state(None, 1, []) is None


def test_one_read_per_chassis(amp):
    """Every zone is its own config entry with its own manager; one read
    serves them all."""
    async def run():
        mgrs = [M.Control4Manager("10.0.0.5", 8750, 0.1) for _ in range(8)]
        return await asyncio.gather(*(m.async_status() for m in mgrs))

    got = asyncio.run(run())
    assert all(g == got[0] for g in got)
    assert got[0]["ain"] == [1, 2, 3, 4, 5, 6, 8, 8] and got[0]["avol"][3] == 0xCD
    assert sorted(amp.asked) == sorted(M.STATUS_COMMANDS)


def test_command_forgets_the_read(amp):
    async def run():
        m = M.Control4Manager("10.0.0.5", 8750, 0.1)
        first = await m.async_status()
        amp.state["ain"][1] = 0
        cached = await m.async_status()
        m.forget_status()
        fresh = await m.async_status()
        return first, cached, fresh

    first, cached, fresh = asyncio.run(run())
    assert first["ain"][1] == 2 and cached["ain"][1] == 2 and fresh["ain"][1] == 0


def test_silent_amp_gives_none(amp):
    amp.silent = True

    async def run():
        return await M.Control4Manager("10.0.0.5", 8750, 0.05).async_status()

    assert asyncio.run(run()) is None
