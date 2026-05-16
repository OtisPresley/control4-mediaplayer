class control4AmpChannel:
    """Represents a channel of a Control 4 Matrix Amp."""

    def __init__(self, manager, channel):
        self._manager = manager
        self._channel = channel
        self._source = 1
        self._volume = 0

    @property
    def channel(self):
        return self._channel

    @property
    def source(self):
        return self._source

    async def async_set_source(self, value):
        self._source = value
        cmd = f"c4.amp.out {int(self._channel):02x} {int(self._source):02x}"
        return await self._manager.async_send_command(cmd)

    @property
    def volume(self):
        return self._volume

    async def async_set_volume(self, value):
        self._volume = value
        # Volume offset formula: hex(percentage + 155)
        new_volume = int(float(self._volume) * 100) + 155
        new_volume_hex = f"{new_volume:02x}"
        cmd = f"c4.amp.chvol {int(self._channel):02x} {new_volume_hex}"
        return await self._manager.async_send_command(cmd)

    async def async_turn_on(self):
        # Disable power save (wake up)
        await self._manager.async_send_command("c4.amp.psave 00 00")
        # Route the input to this channel
        cmd = f"c4.amp.out {int(self._channel):02x} {int(self._source):02x}"
        return await self._manager.async_send_command(cmd)

    async def async_turn_off(self):
        # Isolate/turn off zone by routing input 00
        cmd = f"c4.amp.out {int(self._channel):02x} 00"
        return await self._manager.async_send_command(cmd)

    async def async_mute_volume(self, mute: bool):
        if mute:
            # Set volume to 0 (which is 155 in hex -> 9B)
            cmd = f"c4.amp.chvol {int(self._channel):02x} 9b"
            return await self._manager.async_send_command(cmd)
        else:
            # Restore previous volume
            new_volume = int(float(self._volume) * 100) + 155
            new_volume_hex = f"{new_volume:02x}"
            cmd = f"c4.amp.chvol {int(self._channel):02x} {new_volume_hex}"
            return await self._manager.async_send_command(cmd)
