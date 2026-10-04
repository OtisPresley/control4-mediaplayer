"""Sequence-number behaviour of Control4Manager against an in-process fake amp.

The real amp silently drops any frame whose sequence number equals the last one
it accepted (from any sender). The fake below reproduces exactly that rule.

No real sockets are used (the Home Assistant test plugin disables them): the
``socket`` module that manager.py imported is replaced with a fake whose
``sendto`` applies the amp's rule and whose ``recvfrom`` returns the queued
reply or raises a timeout. Only the stdlib and pytest are needed; manager.py
imports nothing from Home Assistant. Set C4_MANAGER_PATH to run the same tests
against a different manager.py.
"""
import asyncio
import importlib.util
import logging
import os
import re
import socket
import types
from pathlib import Path

import pytest

DEFAULT_MANAGER = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "control4_mediaplayer" / "manager.py"
)


def _load_manager_module():
    path = Path(os.environ.get("C4_MANAGER_PATH", DEFAULT_MANAGER))
    spec = importlib.util.spec_from_file_location("c4_manager_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manager_mod = _load_manager_module()
Control4Manager = manager_mod.Control4Manager

FRAME_RE = re.compile(rb"^0s2a(\d+) ")


class FakeAmp:
    """Amp state: replies '0r2a<NN> n01' and drops a frame whose NN equals the
    last NN it accepted."""

    def __init__(self, preseed_first_frame=False, drop_all=False):
        self.received = []  # every NN seen, including dropped frames
        self.last_accepted = None
        self.drop_all = drop_all
        # Simulate "another sender already used this number": the first frame's
        # NN is treated as already accepted, so that frame is dropped.
        self._preseed_first = preseed_first_frame

    def handle(self, data):
        """Process one frame; return the reply bytes, or None if dropped."""
        m = FRAME_RE.match(data)
        if not m:
            return None
        nn = int(m.group(1))
        self.received.append(nn)
        if self._preseed_first:
            self._preseed_first = False
            self.last_accepted = nn
        if self.drop_all or nn == self.last_accepted:
            return None  # silent drop, exactly like the real amp
        self.last_accepted = nn
        return f"0r2a{nn} n01\r\n".encode()

    def socket_module(self):
        """A stand-in for the `socket` module, as imported by manager.py."""
        amp = self

        class FakeSocket:
            def __init__(self, *args, **kwargs):
                self._replies = []

            def settimeout(self, timeout):
                pass

            def sendto(self, data, addr):
                reply = amp.handle(data)
                if reply is not None:
                    self._replies.append(reply)
                return len(data)

            def recvfrom(self, bufsize):
                if not self._replies:
                    raise TimeoutError("timed out")  # == socket.timeout on 3.10+
                return self._replies.pop(0), ("127.0.0.1", 8750)

            def close(self):
                pass

        return types.SimpleNamespace(
            socket=FakeSocket,
            AF_INET=socket.AF_INET,
            SOCK_DGRAM=socket.SOCK_DGRAM,
            timeout=TimeoutError,
        )


@pytest.fixture
def make_amp(monkeypatch):
    def _make(**kwargs):
        amp = FakeAmp(**kwargs)
        monkeypatch.setattr(manager_mod, "socket", amp.socket_module())
        return amp

    return _make


def _run_commands(commands):
    async def go():
        # Built inside the loop: asyncio.Lock binds to the current loop on 3.9.
        mgr = Control4Manager("127.0.0.1", 8750, udp_timeout=0.05)
        return [await mgr.async_send_command(c) for c in commands]

    return asyncio.run(go())


def test_500_commands_all_get_replies_and_no_repeated_number(make_amp):
    n = 500
    amp = make_amp()
    replies = _run_commands([f"c4.amp.chvol 01 {i % 90 + 155:02x}" for i in range(n)])
    sent = list(amp.received)

    assert None not in replies, f"{replies.count(None)} of {n} commands got no reply"
    assert all(r.startswith("0r2a") for r in replies)
    repeats = [i for i in range(1, len(sent)) if sent[i] == sent[i - 1]]
    assert not repeats, f"sequence number repeated back to back at {len(repeats)} positions"
    assert all(10 <= nn <= 99 for nn in sent)
    assert len(sent) == n  # no retry needed once numbers never repeat


def test_retry_succeeds_with_a_different_number_when_first_number_is_a_repeat(make_amp, caplog):
    amp = make_amp(preseed_first_frame=True)
    with caplog.at_level(logging.DEBUG, logger=manager_mod.__name__):
        (reply,) = _run_commands(["c4.amp.chvol 01 b9"])
    sent = list(amp.received)

    assert reply is not None and reply.startswith("0r2a"), f"no reply; frames seen: {sent}"
    assert len(sent) == 2 and sent[0] != sent[1], sent
    assert any(r.levelno == logging.DEBUG and "retry" in r.getMessage() for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_warning_when_retry_also_gets_no_reply(make_amp, caplog):
    amp = make_amp(drop_all=True)  # both attempts time out
    with caplog.at_level(logging.DEBUG, logger=manager_mod.__name__):
        (res,) = _run_commands(["c4.amp.chvol 01 b9"])
    assert res is None
    assert len(amp.received) == 2
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_non_allowlisted_command_is_never_retried(make_amp):
    # Unknown/raw commands might be relative (up/down/toggle): send exactly once.
    amp = make_amp(preseed_first_frame=True)
    (reply,) = _run_commands(["c4.amp.somerelativething 01"])
    assert reply is None
    assert len(amp.received) == 1
