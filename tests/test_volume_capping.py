import unittest
import sys
from unittest.mock import MagicMock, AsyncMock

# Mock Home Assistant modules before importing our custom component if they are not installed
try:
    import homeassistant
    import homeassistant.config_entries
    import homeassistant.core
except ImportError:
    from types import ModuleType
    
    # 1. Mock homeassistant
    ha = ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha
    
    # 2. Mock homeassistant.config_entries
    ha_ce = ModuleType("homeassistant.config_entries")
    class DummyConfigEntry:
        pass
    ha_ce.ConfigEntry = DummyConfigEntry
    sys.modules["homeassistant.config_entries"] = ha_ce
    
    # 3. Mock homeassistant.core
    ha_core = ModuleType("homeassistant.core")
    class DummyHomeAssistant:
        pass
    ha_core.HomeAssistant = DummyHomeAssistant
    sys.modules["homeassistant.core"] = ha_core
    
    # 4. Mock homeassistant.const
    ha_const = ModuleType("homeassistant.const")
    ha_const.STATE_OFF = "off"
    ha_const.STATE_ON = "on"
    sys.modules["homeassistant.const"] = ha_const
    
    # 5. Mock homeassistant.helpers
    ha_helpers = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = ha_helpers
    
    # 6. Mock homeassistant.helpers.device_registry
    ha_dr = ModuleType("homeassistant.helpers.device_registry")
    ha_dr.DeviceInfo = MagicMock()
    sys.modules["homeassistant.helpers.device_registry"] = ha_dr
    
    # 7. Mock homeassistant.helpers.entity_registry
    ha_er = ModuleType("homeassistant.helpers.entity_registry")
    ha_er.async_get = MagicMock()
    sys.modules["homeassistant.helpers.entity_registry"] = ha_er
    
    # 7b. Mock homeassistant.helpers.restore_state
    ha_rs = ModuleType("homeassistant.helpers.restore_state")
    class DummyRestoreEntity:
        async def async_added_to_hass(self):
            pass
        async def async_get_last_state(self):
            return getattr(self, "_mock_last_state", None)
    ha_rs.RestoreEntity = DummyRestoreEntity
    sys.modules["homeassistant.helpers.restore_state"] = ha_rs
    
    # 8. Mock homeassistant.components
    ha_comp = ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = ha_comp
    
    # 9. Mock homeassistant.components.media_player
    ha_mp = ModuleType("homeassistant.components.media_player")
    class DummyMediaPlayerEntity:
        def async_write_ha_state(self):
            pass
    ha_mp.MediaPlayerEntity = DummyMediaPlayerEntity
    class DummyMediaPlayerEntityFeature:
        VOLUME_SET = 1
        VOLUME_STEP = 2
        TURN_ON = 4
        TURN_OFF = 8
        SELECT_SOURCE = 16
        VOLUME_MUTE = 32
    ha_mp.MediaPlayerEntityFeature = DummyMediaPlayerEntityFeature
    sys.modules["homeassistant.components.media_player"] = ha_mp
    
    # 10. Mock homeassistant.components.number
    ha_num = ModuleType("homeassistant.components.number")
    class DummyNumberEntity:
        def async_write_ha_state(self):
            pass
        @property
        def native_value(self):
            return getattr(self, "_attr_native_value", None)
            
    class DummyRestoreNumber(DummyNumberEntity):
        async def async_added_to_hass(self):
            pass
        async def async_get_last_number_data(self):
            return getattr(self, "_mock_last_number_data", None)
            
    ha_num.NumberEntity = DummyNumberEntity
    ha_num.RestoreNumber = DummyRestoreNumber
    sys.modules["homeassistant.components.number"] = ha_num

# Now import the actual code
from custom_components.control4_mediaplayer.media_player import C4MediaPlayer
from custom_components.control4_mediaplayer.number import C4MaxVolumeNumber
from custom_components.control4_mediaplayer.const import DOMAIN

class TestVolumeCappingAndSync(unittest.IsolatedAsyncioTestCase):
    async def test_volume_capping_and_sync(self):
        # Setup mocks
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        entry.data = {
            "host": "10.0.12.246",
            "port": 8750,
            "channel": 1,
            "zone_custom_name": "Living Room",
            "name": "Matrix Amp",
            "source_list": "Apple TV\nSonos\nSpotify",
            "on_volume": 50,
        }
        
        def mock_async_update_entry(e, data=None, options=None):
            if data is not None:
                e.data.update(data)
        hass.config_entries.async_update_entry = mock_async_update_entry
        
        manager = MagicMock()
        manager.async_send_command = AsyncMock(return_value="OK")
        manager.async_set_max_volume = AsyncMock()
        
        hass.data = {
            DOMAIN: {
                "test_entry_id": {
                    "manager": manager
                }
            }
        }
        
        device_info = MagicMock()
        
        # Instantiate Entities
        media_player = C4MediaPlayer("10.0.12.246", 8750, 1, "Living Room", entry, manager)
        # Give media_player a mock hass
        media_player.hass = hass
        
        # Store media_player in hass.data
        hass.data[DOMAIN]["test_entry_id"]["media_player"] = media_player
        
        max_volume_number = C4MaxVolumeNumber(hass, entry, manager, "10.0.12.246", 1, device_info, "Living Room")
        hass.data[DOMAIN]["test_entry_id"]["max_volume_entity"] = max_volume_number
        
        # 1. Test max volume property retrieval
        self.assertEqual(media_player.max_volume, 1.0)  # Default max volume entity native value is 100 -> 1.0
        
        # 2. Test volume capping in async_set_volume_level
        await media_player.async_set_volume_level(0.8)
        self.assertEqual(media_player.volume_level, 0.8)
        
        # Now set max volume to 40 (meaning 40% -> 0.4)
        await max_volume_number.async_set_native_value(40.0)
        
        # Setting max volume to 40 when current volume is 80% should cap it to 40% (0.4)
        self.assertEqual(media_player.volume_level, 0.4)
        self.assertEqual(max_volume_number.native_value, 40.0)
        
        # Verify the amplifier received set_volume command for 0.4 to sync
        # C4Amp set_volume formula: int(0.4 * 100) + 155 = 195 = hex 0xc3 -> command: c4.amp.chvol 01 c3
        manager.async_send_command.assert_any_call("c4.amp.chvol 01 c3")
        
        # 3. Test volume capping during async_turn_on
        # Let's reset the volume to a safe level under the max
        media_player._volume = 0.2
        # Turn on should use entry's "on_volume" (50) which exceeds max (40), so it caps to 40
        await media_player.async_turn_on()
        self.assertEqual(media_player.volume_level, 0.4)
        self.assertEqual(media_player.state, "on")

        # 4. Test volume capping and hardware bypass when state is "on" (playing)
        # Reset mock calls on manager
        manager.async_set_max_volume.reset_mock()
        manager.async_send_command.reset_mock()
        
        # Current volume is 0.4 (40%). Let's set max volume to 30.0 (30% -> 0.3)
        await max_volume_number.async_set_native_value(30.0)
        
        # Volume should be capped to 0.3
        self.assertEqual(media_player.volume_level, 0.3)
        
        # Since media player is ON (playing), it should NOT set hardware max volume directly (avoiding the brief jump)
        manager.async_set_max_volume.assert_not_called()
        
        # But it should send chvol to cap the active volume
        manager.async_send_command.assert_any_call("c4.amp.chvol 01 b9") # 30 + 155 = 185 = b9
        
        # Now let's turn off the zone. This should safely sync the max volume limit to the hardware.
        manager.async_set_max_volume.reset_mock()
        await media_player.async_turn_off()
        self.assertEqual(media_player.state, "off")
        manager.async_set_max_volume.assert_called_with(1, 30.0)

    async def test_media_player_state_restoration_sync(self):
        # Verify media player state restoration and playing sync on startup
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        entry.data = {
            "host": "10.0.12.246",
            "port": 8750,
            "channel": 1,
            "zone_custom_name": "Living Room",
            "name": "Matrix Amp",
        }
        
        manager = MagicMock()
        manager.async_send_command = AsyncMock(return_value="OK")
        manager.async_set_max_volume = AsyncMock()
        
        hass.data = {
            DOMAIN: {
                "test_entry_id": {
                    "manager": manager
                }
            }
        }
        
        # Instantiate media player
        media_player = C4MediaPlayer("10.0.12.246", 8750, 1, "Living Room", entry, manager)
        media_player.hass = hass
        
        # Setup max volume entity
        device_info = MagicMock()
        max_volume_number = C4MaxVolumeNumber(hass, entry, manager, "10.0.12.246", 1, device_info, "Living Room")
        max_volume_number._attr_native_value = 80.0 # max volume is 80%
        hass.data[DOMAIN]["test_entry_id"]["max_volume_entity"] = max_volume_number
        hass.data[DOMAIN]["test_entry_id"]["media_player"] = media_player
        
        # Setup mock last state: playing (on) at 0.9 (90%) volume
        class DummyState:
            def __init__(self, state, volume_level):
                self.state = state
                self.attributes = {"volume_level": volume_level}
                
        media_player._mock_last_state = DummyState("on", 0.9)
        
        # Restore state on startup
        await media_player.async_added_to_hass()
        
        # Restored volume (0.9) should be capped to max_volume (0.8)
        self.assertEqual(media_player.state, "on")
        self.assertEqual(media_player.volume_level, 0.8)
        
        # It should NOT send any physical sync commands on startup to keep playback uninterrupted
        manager.async_set_max_volume.assert_not_called()
        manager.async_send_command.assert_not_called()

    async def test_native_mute_success(self):
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        entry.data = {"host": "10.0.12.246", "port": 8750, "channel": 1}
        
        manager = MagicMock()
        # Native mute succeeds and returns a matched ACK prefix with "000"
        manager.async_send_command = AsyncMock(return_value="0r2a49 000")
        
        media_player = C4MediaPlayer("10.0.12.246", 8750, 1, "Living Room", entry, manager)
        media_player.hass = hass
        media_player._volume = 0.25
        
        await media_player.async_mute_volume(True)
        
        # Verify native mute command was called and not volume command
        manager.async_send_command.assert_called_with("c4.amp.mute 01 01")
        self.assertTrue(media_player.is_volume_muted)
        
    async def test_native_mute_fallback(self):
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        entry.data = {"host": "10.0.12.246", "port": 8750, "channel": 1}
        
        manager = MagicMock()
        # Native mute returns None (timeout) or "n01" (error/not supported)
        manager.async_send_command = AsyncMock(return_value=None)
        
        media_player = C4MediaPlayer("10.0.12.246", 8750, 1, "Living Room", entry, manager)
        media_player.hass = hass
        media_player._volume = 0.25
        
        await media_player.async_mute_volume(True)
        
        # Verify it fell back to volume-based mute (sets volume to 9b)
        manager.async_send_command.assert_any_call("c4.amp.mute 01 01")
        manager.async_send_command.assert_any_call("c4.amp.chvol 01 9b")
        self.assertTrue(media_player.is_volume_muted)

    async def test_optional_eq_entities(self):
        # 1. Verify EQ entities are NOT created if enable_eq is False
        from custom_components.control4_mediaplayer.number import async_setup_entry
        
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        entry.data = {
            "host": "10.0.12.246",
            "port": 8750,
            "channel": 1,
            "zone_custom_name": "Living Room",
            "name": "Matrix Amp",
            "enable_eq": False,
        }
        
        def mock_async_update_entry(e, data=None, options=None):
            if data is not None:
                e.data.update(data)
        hass.config_entries.async_update_entry = mock_async_update_entry
        
        manager = MagicMock()
        hass.data = {
            DOMAIN: {
                "test_entry_id": {
                    "manager": manager
                }
            }
        }
        
        registered_entities = []
        def mock_add_entities(entities, update_before_add=False):
            registered_entities.extend(entities)
            
        await async_setup_entry(hass, entry, mock_add_entities)
        
        # Should only have C4MaxVolumeNumber
        self.assertEqual(len(registered_entities), 1)
        self.assertEqual(registered_entities[0].__class__.__name__, "C4MaxVolumeNumber")
        
        # 2. Verify EQ entities ARE created if enable_eq is True
        entry.data["enable_eq"] = True
        registered_entities.clear()
        
        await async_setup_entry(hass, entry, mock_add_entities)
        
        self.assertEqual(len(registered_entities), 4)
        entity_classes = [e.__class__.__name__ for e in registered_entities]
        self.assertIn("C4MaxVolumeNumber", entity_classes)
        self.assertEqual(entity_classes.count("C4EQNumber"), 3)
        
        # Find the treble, bass, balance entities by config key
        treble_entity = next(e for e in registered_entities if getattr(e, "_config_key", None) == "treble")
        bass_entity = next(e for e in registered_entities if getattr(e, "_config_key", None) == "bass")
        bal_entity = next(e for e in registered_entities if getattr(e, "_config_key", None) == "balance")
        
        # Test C4TrebleNumber sends c4.amp.trebgain command
        manager.async_send_command = AsyncMock()
        await treble_entity.async_set_native_value(3.0)
        self.assertEqual(treble_entity.native_value, 3.0)
        # two's complement: 3 = 03 -> c4.amp.trebgain 01 03
        manager.async_send_command.assert_called_with("c4.amp.trebgain 01 03")
        
        # Test C4BassNumber sends c4.amp.bassgain command
        manager.async_send_command = AsyncMock()
        await bass_entity.async_set_native_value(-5.0)
        self.assertEqual(bass_entity.native_value, -5.0)
        # two's complement: -5 = fb -> c4.amp.bassgain 01 fb
        manager.async_send_command.assert_called_with("c4.amp.bassgain 01 fb")
        
        # Test C4BalanceNumber sends c4.amp.bal command
        manager.async_send_command = AsyncMock()
        await bal_entity.async_set_native_value(4.0)
        self.assertEqual(bal_entity.native_value, 4.0)
        # two's complement: 4 = 04 -> c4.amp.bal 01 04
        manager.async_send_command.assert_called_with("c4.amp.bal 01 04")

        # 3. Verify state restoration from RestoreNumber
        class DummyNumberData:
            def __init__(self, val):
                self.native_value = val
                
        # Mock last saved state
        treble_entity._mock_last_number_data = DummyNumberData(5.0)
        bass_entity._mock_last_number_data = DummyNumberData(-2.0)
        bal_entity._mock_last_number_data = DummyNumberData(-1.0)
        
        # Call async_added_to_hass to trigger restoration
        manager.async_send_command = AsyncMock()
        await treble_entity.async_added_to_hass()
        await bass_entity.async_added_to_hass()
        await bal_entity.async_added_to_hass()
        
        # Assert restored values are loaded and synced to hardware
        self.assertEqual(treble_entity.native_value, 5.0)
        manager.async_send_command.assert_any_call("c4.amp.trebgain 01 05")
        
        self.assertEqual(bass_entity.native_value, -2.0)
        manager.async_send_command.assert_any_call("c4.amp.bassgain 01 fe")
        
        self.assertEqual(bal_entity.native_value, -1.0)
        manager.async_send_command.assert_any_call("c4.amp.bal 01 ff")

if __name__ == "__main__":
    unittest.main()
