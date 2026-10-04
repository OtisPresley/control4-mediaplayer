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
            except (TimeoutError, socket.timeout):
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



