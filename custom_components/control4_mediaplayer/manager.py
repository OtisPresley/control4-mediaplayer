import asyncio
import logging
import random
import socket

_LOGGER = logging.getLogger(__name__)

# The amp silently drops any frame whose sequence number equals the last one it
# accepted (from any sender), so a command can be lost with no reply at all.
SEQ_MIN = 10
SEQ_MAX = 99

# Commands that set an absolute value and are therefore safe to resend if the
# reply (rather than the command) was lost. Anything not listed here (for
# example a free-form send_raw_command) is sent once and never retried, since
# it could be a relative command (volume up/down, toggle).
_IDEMPOTENT_COMMANDS = frozenset(
    {
        "c4.amp.psave",
        "c4.amp.out",
        "c4.amp.chvol",
        "c4.amp.chvolmax",
        "c4.amp.chmode",
        "c4.amp.ingain",
        "c4.amp.mute",
        "c4.amp.trebgain",
        "c4.amp.bassgain",
        "c4.amp.bal",
    }
)


# ── reading the amp back ─────────────────────────────────────────────────────
# The amp answers GET frames ("0g<seq> <command>") with its live values:
#   c4.amp.ain   the input each zone is routed to (00 = off), one byte a zone
#   c4.amp.avol  each zone's volume, percent + 155
#   c4.amp.amut  each zone's mute flag
# Checked on two C4-16AMP3-B, firmware 03.26.52. One read serves every zone of
# a chassis (the zones are separate config entries with separate managers),
# so it is shared per host and kept for STATUS_MAX_AGE seconds.
STATUS_COMMANDS = ("c4.amp.ain", "c4.amp.avol", "c4.amp.amut")
STATUS_MAX_AGE = 5.0
_STATUS_CACHE: dict = {}
_STATUS_LOCKS: dict = {}


def parse_list_reply(reply, command):
    """The hex bytes after `command` in a GET reply, as ints; None unless OK.

    "0r4e03 000 c4.amp.ain 01 02 03 04 05 06 08 08" -> [1, 2, 3, 4, 5, 6, 8, 8]
    """
    if not reply:
        return None
    parts = reply.split()
    if len(parts) < 3 or parts[1] != "000" or command not in parts:
        return None
    out = []
    for tok in parts[parts.index(command) + 1:]:
        try:
            out.append(int(tok, 16))
        except ValueError:
            return None
    return out or None


def zone_state(status, channel, source_list):
    """One zone's live state from a chassis status, or None when unknown.

    {"on", "source_index" (1-based input), "source" (its name or None),
     "volume" (0-1), "muted"}
    """
    if not status:
        return None
    i = int(channel) - 1
    ain, avol, amut = status.get("ain"), status.get("avol"), status.get("amut")
    if not ain or i < 0 or i >= len(ain):
        return None
    out = {"on": ain[i] != 0, "source_index": ain[i] or None, "source": None, "volume": None, "muted": None}
    if ain[i] and source_list and ain[i] <= len(source_list):
        out["source"] = source_list[ain[i] - 1]
    if avol and i < len(avol):
        out["volume"] = max(0.0, min(1.0, (avol[i] - 155) / 100.0))
    if amut and i < len(amut):
        out["muted"] = amut[i] == 1
    return out


class Control4Manager:
    """Centralized manager for Control4 Matrix Amp UDP communication."""
    
    def __init__(self, host: str, port: int, udp_timeout: float = 2.0):
        self.host = host
        self.port = port
        self.udp_timeout = udp_timeout
        self._lock = asyncio.Lock()
        # Random start so a restart does not predictably reuse the last number.
        self._seq = random.randint(SEQ_MIN, SEQ_MAX)

    def _next_counter(self) -> str:
        """Return the next sequence prefix, never equal to the previous one."""
        self._seq = SEQ_MIN + (self._seq - SEQ_MIN + 1) % (SEQ_MAX - SEQ_MIN + 1)
        return f"0s2a{self._seq}"

    async def async_send_command(self, command: str):
        """Send a UDP command to the amplifier using Safe Transport logic."""
        async with self._lock:
            can_retry = command.split(" ", 1)[0] in _IDEMPOTENT_COMMANDS
            res, timed_out = await self._async_send_once(command)

            if res is None and timed_out and can_retry:
                _LOGGER.debug(
                    "No reply from %s:%s to %r; retrying once with a new sequence number",
                    self.host, self.port, command,
                )
                res, timed_out = await self._async_send_once(command)
                if res is None and timed_out:
                    _LOGGER.warning(
                        "No reply from %s:%s to %r after retry", self.host, self.port, command
                    )
            return res

    async def _async_send_once(self, command: str):
        """Send one frame; return (reply or None, whether it timed out)."""
        counter = self._next_counter()
        payload = f"{counter} {command} \r\n"

        loop = asyncio.get_running_loop()

        def _send_and_wait():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.udp_timeout)

            try:
                sock.sendto(payload.encode('utf-8'), (self.host, self.port))
                while True:
                    data, _ = sock.recvfrom(1024)
                    received = data.decode('utf-8').strip()
                    # Ensure we are capturing the response to our specific command
                    expected_prefix = counter.replace("s", "r", 1)
                    if received.startswith(expected_prefix):
                        return received, False
            except TimeoutError:
                # Timeout is an expected fallback condition for the amp if it doesn't ack
                return None, True
            except Exception as e:
                _LOGGER.error("Error sending UDP to %s:%s - %s", self.host, self.port, e)
                return None, False
            finally:
                sock.close()

        res = await loop.run_in_executor(None, _send_and_wait)

        # 10ms hardware guard delay to prevent packet drops on legacy network cards
        await asyncio.sleep(0.01)
        return res


    async def async_set_max_volume(self, zone: int, volume: float):
        """Set max volume (0 to 100)."""
        zone_hex = f"{int(zone):02x}"
        vol_hex = f"{int(volume + 155):02x}"
        await self.async_send_command(f"c4.amp.chvolmax {zone_hex} {vol_hex}")

    async def async_set_mode(self, zone: int, mode_str: str):
        """Set output topology mode."""
        zone_hex = f"{int(zone):02x}"
        modes = {"stereo": "00", "mono_summed": "01", "bridged_mono": "02"}
        mode_hex = modes.get(mode_str.lower(), "00")
        await self.async_send_command(f"c4.amp.chmode {zone_hex} {mode_hex}")

    # Phase 2 Commands
    async def async_set_power_save(self, active: bool):
        """Set system power save mode."""
        val = "01 00" if active else "00 00"
        await self.async_send_command(f"c4.amp.psave {val}")




    async def async_set_input_gain(self, input_num: int, level: float):
        """Set input gain trim (-6 to +6 dB)."""
        input_hex = f"{int(input_num):02x}"
        # Scale: 80 = 0dB. Limits: 7A (-6dB) to 86 (+6dB)
        gain_hex = f"{int(128 + level):02x}"
        await self.async_send_command(f"c4.amp.ingain {input_hex} {gain_hex}")

    async def async_query(self, command: str):
        """Send one GET frame; the reply line, or None.

        GETs use their own random 4-hex sequence ("0g1a2b"): the amp drops a
        frame whose number equals the last one it accepted, and the SET
        counter ("0s2aNN") never takes this shape.
        """
        seq = f"{random.randint(0x1000, 0xfff0):04x}"
        payload = f"0g{seq} {command}\r\n"
        want = f"0r{seq}"
        loop = asyncio.get_running_loop()

        def _ask():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.udp_timeout)
            try:
                sock.sendto(payload.encode("utf-8"), (self.host, self.port))
                while True:
                    data, _ = sock.recvfrom(1024)
                    text = data.decode("utf-8", "replace").strip()
                    if text.startswith(want):
                        return text
            except (TimeoutError, OSError):
                return None
            finally:
                sock.close()

        async with self._lock:
            res = await loop.run_in_executor(None, _ask)
            await asyncio.sleep(0.01)
            return res

    async def async_status(self, max_age: float = STATUS_MAX_AGE):
        """The chassis' live routing, volumes and mutes, read at most once
        per `max_age` seconds for all its zones: {"ain", "avol", "amut"} as
        lists of ints, or None when the amp did not answer."""
        key = (self.host, self.port)
        lock = _STATUS_LOCKS.setdefault(key, asyncio.Lock())
        async with lock:
            loop = asyncio.get_running_loop()
            hit = _STATUS_CACHE.get(key)
            if hit and loop.time() - hit[0] < max_age:
                return hit[1]
            out = {}
            for command in STATUS_COMMANDS:
                values = parse_list_reply(await self.async_query(command), command)
                out[command.rsplit(".", 1)[1]] = values
            status = out if out.get("ain") else None
            if status is None:
                _LOGGER.debug("No status from %s:%s", self.host, self.port)
            _STATUS_CACHE[key] = (loop.time(), status)
            return status

    def forget_status(self):
        """Drop the shared read after a command, so the next poll reads anew."""
        _STATUS_CACHE.pop((self.host, self.port), None)
