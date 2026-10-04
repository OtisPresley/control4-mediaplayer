"""Sequence-number behaviour of Control4Manager against a fake amp.

The real amp silently drops any frame whose sequence number equals the last one
it accepted (from any sender). The fake amp below reproduces exactly that.

Uses only the stdlib and pytest; manager.py imports nothing from Home Assistant.
Set C4_MANAGER_PATH to run the same tests against a different manager.py.
"""
import asyncio
import importlib.util
import logging
import os
import re
import socket
import threading
from pathlib import Path

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
    """UDP listener on 127.0.0.1 that replies '0r2a<NN> n01' and drops a frame
    whose NN equals the last NN it accepted."""

    def __init__(self, preseed_first_frame=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.05)
        self.port = self.sock.getsockname()[1]
        self.received = []  # every NN seen, including dropped frames
        self.accepted = []
        self.last_accepted = None
        # Simulate "another sender already used this number": the first frame's
        # NN is treated as already accepted, so that frame is dropped.
        self._preseed_first = preseed_first_frame
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                return
            m = FRAME_RE.match(data)
            if not m:
                continue
            nn = int(m.group(1))
            self.received.append(nn)
            if self._preseed_first:
                self._preseed_first = False
                self.last_accepted = nn
            if nn == self.last_accepted:
                continue  # silent drop, exactly like the real amp
            self.last_accepted = nn
            self.accepted.append(nn)
            self.sock.sendto(f"0r2a{nn} n01\r\n".encode(), addr)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2)
        self.sock.close()


def _run_commands(amp, commands, timeout=0.05):
    async def go():
        # Built inside the loop: asyncio.Lock binds to the current loop on 3.9.
        mgr = Control4Manager("127.0.0.1", amp.port, udp_timeout=timeout)
        return [await mgr.async_send_command(c) for c in commands]

    return asyncio.run(go())


def test_500_commands_all_get_replies_and_no_repeated_number():
    n = 500
    with FakeAmp() as amp:
        replies = _run_commands(amp, [f"c4.amp.chvol 01 {i % 90 + 155:02x}" for i in range(n)])
        sent = list(amp.received)

    assert None not in replies, f"{replies.count(None)} of {n} commands got no reply"
    assert all(r.startswith("0r2a") for r in replies)
    repeats = [i for i in range(1, len(sent)) if sent[i] == sent[i - 1]]
    assert not repeats, f"sequence number repeated back to back at {len(repeats)} positions"
    assert all(10 <= nn <= 99 for nn in sent)
    assert len(sent) == n  # no retry needed once numbers never repeat


def test_retry_succeeds_with_a_different_number_when_first_number_is_a_repeat(caplog):
    with FakeAmp(preseed_first_frame=True) as amp:
        with caplog.at_level(logging.DEBUG, logger=manager_mod.__name__):
            (reply,) = _run_commands(amp, ["c4.amp.chvol 01 b9"])
        sent = list(amp.received)

    assert reply is not None and reply.startswith("0r2a"), f"no reply; frames seen: {sent}"
    assert len(sent) == 2 and sent[0] != sent[1], sent
    assert any(r.levelno == logging.DEBUG and "retry" in r.getMessage() for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_warning_when_retry_also_gets_no_reply(caplog):
    # A listener that never replies: both attempts time out.
    dead = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dead.bind(("127.0.0.1", 0))
    try:
        async def go():
            mgr = Control4Manager("127.0.0.1", dead.getsockname()[1], udp_timeout=0.05)
            return await mgr.async_send_command("c4.amp.chvol 01 b9")

        with caplog.at_level(logging.DEBUG, logger=manager_mod.__name__):
            res = asyncio.run(go())
    finally:
        dead.close()
    assert res is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_non_allowlisted_command_is_never_retried():
    # Unknown/raw commands might be relative (up/down/toggle): send exactly once.
    with FakeAmp(preseed_first_frame=True) as amp:
        (reply,) = _run_commands(amp, ["c4.amp.somerelativething 01"])
        sent = list(amp.received)
    assert reply is None
    assert len(sent) == 1
