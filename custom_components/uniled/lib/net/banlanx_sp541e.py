"""UniLED NET Devices - BanlanX SP541E."""
from __future__ import annotations

from typing import Any, Final

from ..const import *  # I know!
from ..channel import UniledChannel
from ..features import (
    LightStripFeature,
    EffectTypeFeature,
    EffectLoopFeature,
    EffectPlayFeature,
    EffectSpeedFeature,
    EffectLengthFeature,
    EffectDirectionFeature,
    AudioInputFeature,
    AudioSensitivityFeature,
    LightModeFeature,
)
from ..effects import (
    UNILEDEffectType,
    UNILEDEffects,
)
from ..device import ParseNotificationError
from .device import UniledNetDevice, UniledNetModel

import logging

_LOGGER = logging.getLogger(__name__)

SP541E_DEFAULT_KEY: Final = 0x58
SP541E_DEFAULT_PORT: Final = 8587

SP541E_HEADER: Final = bytearray(b"SPTECH\x00")
SP541E_HEADER_LENGTH: Final = 13

MODE_STATIC_COLOR: Final = 0x01
MODE_STATIC_WHITE: Final = 0x02
MODE_DYNAMIC_COLOR: Final = 0x03
MODE_DYNAMIC_WHITE: Final = 0x04
MODE_SOUND_COLOR: Final = 0x05
MODE_SOUND_WHITE: Final = 0x06
MODE_CUSTOM_COLOR: Final = 0x07

SP541E_LIGHT_MODES: Final = {
    MODE_STATIC_COLOR: "Static Color",
    MODE_STATIC_WHITE: "Static White",
    MODE_DYNAMIC_COLOR: "Dynamic Color",
    MODE_DYNAMIC_WHITE: "Dynamic White",
    MODE_SOUND_COLOR: "Sound - Color",
    MODE_SOUND_WHITE: "Sound - White",
    MODE_CUSTOM_COLOR: "Custom",
}

SP541E_ONOFF_EFFECTS: Final = {
    0x01: UNILEDEffects.FLOW_FORWARD,
    0x02: UNILEDEffects.FLOW_BACKWARD,
    0x03: UNILEDEffects.GRADIENT,
    0x04: UNILEDEffects.STARS,
}

SP541E_ONOFF_SPEEDS: Final = {
    0x01: "Slow",
    0x02: "Medium",
    0x03: "Fast",
}

SP541E_ON_POWER: Final = {
    0x00: "Light Off",
    0x01: "Light On",
    0x02: "Last state",
}

SP541E_AUDIO_INPUTS: Final = {
    0x00: UNILED_AUDIO_INPUT_INTMIC,
    0x01: UNILED_AUDIO_INPUT_PLAYER,
    0x02: UNILED_AUDIO_INPUT_EXTMIC,
}

SP541E_MIN_ONOFF_PIXELS: Final = 1
SP541E_MAX_ONOFF_PIXELS: Final = 600
SP541E_MAX_EFFECT_SPEED: Final = 10
SP541E_MAX_EFFECT_LENGTH: Final = 150
SP541E_MAX_SENSITIVITY: Final = 16
SP541E_EFFECTS: Final = {idx: f"Effect {idx}" for idx in range(1, 256)}


class BanlanXSP541ENet(UniledNetModel):
    """Minimal BanlanX SP541E network protocol support."""

    def parse_notifications(
        self, device: UniledNetDevice, sender: int, data: bytearray
    ) -> bool:
        """Parse status response packet(s)."""
        if len(data) < SP541E_HEADER_LENGTH:
            raise ParseNotificationError("SP541E packet too short")

        if data[0:7] != SP541E_HEADER:
            raise ParseNotificationError("SP541E packet header mismatch")

        payload_length = int.from_bytes(data[11:13], byteorder="big")
        expected = SP541E_HEADER_LENGTH + payload_length
        if len(data) != expected:
            raise ParseNotificationError(
                f"SP541E packet size mismatch: got={len(data)} expected={expected}"
            )

        # Known full status packet uses indexes through at least 63.
        if len(data) < 64:
            raise ParseNotificationError(
                f"SP541E status packet too short for parser: {len(data)}"
            )

        light_type = data[27]
        onoff_effect = self.str_if_key_in(data[28], SP541E_ONOFF_EFFECTS, UNILED_UNKNOWN)
        onoff_speed = self.str_if_key_in(data[29], SP541E_ONOFF_SPEEDS, UNILED_UNKNOWN)
        onoff_pixels = int.from_bytes(data[30:32], byteorder="big")
        coexistence = bool(data[32])
        on_power = self.str_if_key_in(data[33], SP541E_ON_POWER, UNILED_UNKNOWN)

        power = bool(data[40])
        loop = data[41]
        mode = data[43]
        effect = data[44]
        play = bool(data[45])
        color_level = data[46]
        white_level = data[47]
        speed = data[53]
        length = data[54]
        direction = bool(data[55])
        gain = data[56]
        input_id = data[57]

        static_rgb = (data[48], data[49], data[50])
        static_cw = data[51]
        static_ww = data[52]

        effect_rgb = (data[58], data[59], data[60])
        effect_cw = data[61]
        effect_ww = data[62]

        firmware = data[19:27].decode("utf-8", errors="ignore").strip() or UNILED_UNKNOWN
        effect_type = UNILEDEffectType.DYNAMIC
        if mode in (MODE_STATIC_COLOR, MODE_STATIC_WHITE):
            effect_type = UNILEDEffectType.STATIC
        elif mode in (MODE_SOUND_COLOR, MODE_SOUND_WHITE):
            effect_type = UNILEDEffectType.SOUND

        supported_color_modes: set[str] = {COLOR_MODE_BRIGHTNESS}
        color_mode = COLOR_MODE_BRIGHTNESS
        rgb_color = None
        white = None
        rgbw = None
        rgbww = None

        if mode in (MODE_STATIC_COLOR, MODE_DYNAMIC_COLOR, MODE_SOUND_COLOR, MODE_CUSTOM_COLOR):
            rgb_color = static_rgb if mode == MODE_STATIC_COLOR else effect_rgb
            supported_color_modes = {COLOR_MODE_RGB}
            color_mode = COLOR_MODE_RGB
        elif mode in (MODE_STATIC_WHITE, MODE_DYNAMIC_WHITE, MODE_SOUND_WHITE):
            white = white_level
            if coexistence:
                rgbww = (
                    static_rgb[0],
                    static_rgb[1],
                    static_rgb[2],
                    static_cw,
                    static_ww,
                )
                supported_color_modes = {COLOR_MODE_RGBWW}
                color_mode = COLOR_MODE_RGBWW
            elif static_rgb != (0, 0, 0):
                rgbw = (static_rgb[0], static_rgb[1], static_rgb[2], white_level)
                supported_color_modes = {COLOR_MODE_RGBW}
                color_mode = COLOR_MODE_RGBW
            else:
                supported_color_modes = {COLOR_MODE_WHITE}
                color_mode = COLOR_MODE_WHITE

        device.master.status.replace(
            {
                ATTR_UL_DEVICE_FORCE_REFRESH: True,
                ATTR_UL_INFO_FIRMWARE: firmware,
                ATTR_UL_INFO_HARDWARE: self.description,
                ATTR_UL_INFO_MODEL_NAME: self.model_name,
                ATTR_UL_INFO_MANUFACTURER: self.manufacturer,
                ATTR_UL_POWER: power,
                ATTR_UL_LIGHT_TYPE: f"Type {hex(light_type)}",
                ATTR_UL_LIGHT_MODE_NUMBER: mode,
                ATTR_UL_LIGHT_MODE: self.str_if_key_in(mode, SP541E_LIGHT_MODES, UNILED_UNKNOWN),
                ATTR_UL_EFFECT_NUMBER: effect,
                ATTR_HA_EFFECT: f"Effect {effect}",
                ATTR_UL_EFFECT_TYPE: str(effect_type),
                ATTR_UL_EFFECT_LOOP: bool(loop),
                ATTR_UL_EFFECT_PLAY: play,
                ATTR_UL_EFFECT_SPEED: speed,
                ATTR_UL_EFFECT_LENGTH: length,
                ATTR_UL_EFFECT_DIRECTION: direction,
                ATTR_UL_ONOFF_EFFECT: onoff_effect,
                ATTR_UL_ONOFF_SPEED: onoff_speed,
                ATTR_UL_ONOFF_PIXELS: onoff_pixels,
                ATTR_UL_ON_POWER: on_power,
                ATTR_UL_COEXISTENCE: coexistence,
                ATTR_UL_SENSITIVITY: gain if mode in (MODE_SOUND_COLOR, MODE_SOUND_WHITE) else None,
                ATTR_UL_AUDIO_INPUT: self.str_if_key_in(
                    input_id, SP541E_AUDIO_INPUTS, UNILED_UNKNOWN
                )
                if mode in (MODE_SOUND_COLOR, MODE_SOUND_WHITE)
                else None,
                ATTR_HA_BRIGHTNESS: white_level if mode in (MODE_STATIC_WHITE, MODE_DYNAMIC_WHITE, MODE_SOUND_WHITE) else color_level,
                ATTR_HA_SUPPORTED_COLOR_MODES: supported_color_modes,
                ATTR_HA_COLOR_MODE: color_mode,
                ATTR_HA_RGB_COLOR: rgb_color,
                ATTR_HA_WHITE: white,
                ATTR_HA_RGBW_COLOR: rgbw,
                ATTR_HA_RGBWW_COLOR: rgbww,
                "effect_cw_ww": (effect_cw, effect_ww),
            }
        )

        if not device.master.features:
            device.master.features = [
                LightStripFeature(extra=UNILED_CONTROL_ATTRIBUTES),
                LightModeFeature(),
                EffectTypeFeature(),
                EffectLoopFeature(),
                EffectPlayFeature(),
                EffectSpeedFeature(SP541E_MAX_EFFECT_SPEED),
                EffectLengthFeature(SP541E_MAX_EFFECT_LENGTH),
                EffectDirectionFeature(),
                AudioInputFeature(),
                AudioSensitivityFeature(SP541E_MAX_SENSITIVITY),
            ]

        return True

    def build_state_query(self, device: UniledNetDevice) -> bytearray | None:
        """Build a state query message."""
        return self._encode(0x02, bytearray([0x01]))

    def build_on_connect(self, device: UniledNetDevice) -> list[bytearray] | None:
        """Build startup command list."""
        return None

    def build_onoff_command(
        self, device: UniledNetDevice, channel: UniledChannel, state: bool
    ) -> bytearray | None:
        """Build power command."""
        return self._encode(0x50, bytearray([0x01 if state else 0x00]))

    def build_brightness_command(
        self, device: UniledNetDevice, channel: UniledChannel, level: int
    ) -> bytearray | None:
        """Build brightness command."""
        which = 0x00 if self._is_color_mode(channel) else 0x01
        return self._encode(0x51, bytearray([which, int(level) & 0xFF]))

    def build_white_command(
        self, device: UniledNetDevice, channel: UniledChannel, level: int
    ) -> bytearray | None:
        """Build white-level command."""
        return self._encode(0x51, bytearray([0x01, int(level) & 0xFF]))

    def build_rgb_color_command(
        self, device: UniledNetDevice, channel: UniledChannel, rgb: tuple[int, int, int]
    ) -> bytearray | None:
        """Build RGB command."""
        red, green, blue = rgb
        if channel.status.light_mode_number in (MODE_STATIC_COLOR, MODE_STATIC_WHITE):
            level = channel.status.brightness if channel.status.brightness else 0xFF
            return self._encode(0x52, bytearray([red, green, blue, level]))
        return self._encode(0x57, bytearray([red, green, blue]))

    def build_rgbw_color_command(
        self,
        device: UniledNetDevice,
        channel: UniledChannel,
        rgbw: tuple[int, int, int, int],
    ) -> list[bytearray] | None:
        """Build RGBW command list."""
        red, green, blue, white = rgbw
        return [
            self.build_rgb_color_command(device, channel, (red, green, blue)),
            self.build_white_command(device, channel, white),
        ]

    def build_rgbww_color_command(
        self,
        device: UniledNetDevice,
        channel: UniledChannel,
        rgbww: tuple[int, int, int, int, int],
    ) -> list[bytearray] | None:
        """Build RGBWW command list."""
        red, green, blue, cold, warm = rgbww
        return [
            self.build_rgb_color_command(device, channel, (red, green, blue)),
            self._encode(0x61, bytearray([cold, warm])),
        ]

    def build_light_mode_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: Any
    ) -> bytearray | list[bytearray] | None:
        """Build light mode command."""
        if isinstance(value, str):
            mode = self.int_if_str_in(value, SP541E_LIGHT_MODES, channel.status.light_mode_number)
        else:
            mode = int(value)
        if mode not in SP541E_LIGHT_MODES:
            return None
        effect = channel.status.effect_number if channel.status.effect_number else 0x01
        commands = [self._encode(0x53, bytearray([mode, effect]))]
        commands.append(self.build_state_query(device))
        return commands

    def fetch_light_mode_list(
        self, device: UniledNetDevice, channel: UniledChannel
    ) -> list | None:
        """Return supported light mode names."""
        return list(SP541E_LIGHT_MODES.values())

    def build_effect_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: Any
    ) -> bytearray | None:
        """Build effect-change command."""
        try:
            effect = int(value)
        except (TypeError, ValueError):
            if isinstance(value, str) and value.lower().startswith("effect "):
                try:
                    effect = int(value.split(" ", 1)[1])
                except (TypeError, ValueError):
                    return None
            else:
                return None
        mode = channel.status.light_mode_number
        if mode not in SP541E_LIGHT_MODES:
            mode = MODE_DYNAMIC_COLOR
        return self._encode(0x53, bytearray([mode, effect & 0xFF]))

    def fetch_effect_list(
        self, device: UniledNetDevice, channel: UniledChannel
    ) -> list | None:
        """Return a generic effect list."""
        return list(SP541E_EFFECTS.values())

    def build_effect_speed_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: int
    ) -> bytearray | None:
        """Build effect speed command."""
        speed = int(value) & 0xFF
        if not 1 <= speed <= SP541E_MAX_EFFECT_SPEED:
            return None
        return self._encode(0x54, bytearray([speed]))

    def build_effect_length_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: int
    ) -> bytearray | None:
        """Build effect length command."""
        length = int(value) & 0xFF
        if not 1 <= length <= SP541E_MAX_EFFECT_LENGTH:
            return None
        return self._encode(0x55, bytearray([length]))

    def build_effect_direction_command(
        self, device: UniledNetDevice, channel: UniledChannel, state: bool
    ) -> bytearray | None:
        """Build effect direction command."""
        return self._encode(0x56, bytearray([0x01 if state else 0x00]))

    def build_effect_loop_command(
        self, device: UniledNetDevice, channel: UniledChannel, state: bool
    ) -> bytearray | None:
        """Build effect loop command."""
        return self._encode(0x58, bytearray([0x01 if state else 0x00]))

    def build_effect_play_command(
        self, device: UniledNetDevice, channel: UniledChannel, state: bool
    ) -> bytearray | None:
        """Build effect play/pause command."""
        return self._encode(0x5D, bytearray([0x01 if state else 0x00]))

    def build_audio_input_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: str
    ) -> bytearray | None:
        """Build audio-input command."""
        input_id = self.int_if_str_in(str(value), SP541E_AUDIO_INPUTS, 0x00)
        return self._encode(0x59, bytearray([input_id]))

    def fetch_audio_input_list(
        self, device: UniledNetDevice, channel: UniledChannel
    ) -> list | None:
        """Return list of supported audio inputs."""
        return list(SP541E_AUDIO_INPUTS.values())

    def build_sensitivity_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: int
    ) -> bytearray | None:
        """Build sensitivity command."""
        gain = int(value) & 0xFF
        if not 1 <= gain <= SP541E_MAX_SENSITIVITY:
            return None
        return self._encode(0x5A, bytearray([gain]))

    def build_onoff_effect_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: str
    ) -> bytearray | None:
        """Build on/off effect command."""
        effect = self.int_if_str_in(value, SP541E_ONOFF_EFFECTS, 0x01)
        speed = self.int_if_str_in(channel.status.onoff_speed, SP541E_ONOFF_SPEEDS, 0x02)
        pixels = channel.status.onoff_pixels if channel.status.onoff_pixels else 60
        if pixels < SP541E_MIN_ONOFF_PIXELS:
            pixels = SP541E_MIN_ONOFF_PIXELS
        if pixels > SP541E_MAX_ONOFF_PIXELS:
            pixels = SP541E_MAX_ONOFF_PIXELS
        return self._encode(
            0x08, bytearray([0x01, effect, speed]) + bytearray(int(pixels).to_bytes(2, "big"))
        )

    def fetch_onoff_effect_list(
        self, device: UniledNetDevice, channel: UniledChannel
    ) -> list | None:
        """Return on/off effect options."""
        return list(SP541E_ONOFF_EFFECTS.values())

    def build_onoff_speed_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: str
    ) -> bytearray | None:
        """Build on/off speed command."""
        effect = self.int_if_str_in(channel.status.onoff_effect, SP541E_ONOFF_EFFECTS, 0x01)
        speed = self.int_if_str_in(value, SP541E_ONOFF_SPEEDS, 0x02)
        pixels = channel.status.onoff_pixels if channel.status.onoff_pixels else 60
        return self._encode(
            0x08, bytearray([0x01, effect, speed]) + bytearray(int(pixels).to_bytes(2, "big"))
        )

    def fetch_onoff_speed_list(
        self, device: UniledNetDevice, channel: UniledChannel
    ) -> list | None:
        """Return on/off speed options."""
        return list(SP541E_ONOFF_SPEEDS.values())

    def build_onoff_pixels_command(
        self, device: UniledNetDevice, channel: UniledChannel, pixels: int
    ) -> bytearray | None:
        """Build on/off pixels command."""
        if not SP541E_MIN_ONOFF_PIXELS <= pixels <= SP541E_MAX_ONOFF_PIXELS:
            return None
        effect = self.int_if_str_in(channel.status.onoff_effect, SP541E_ONOFF_EFFECTS, 0x01)
        speed = self.int_if_str_in(channel.status.onoff_speed, SP541E_ONOFF_SPEEDS, 0x02)
        return self._encode(
            0x08, bytearray([0x01, effect, speed]) + bytearray(int(pixels).to_bytes(2, "big"))
        )

    def build_on_power_command(
        self, device: UniledNetDevice, channel: UniledChannel, value: Any
    ) -> bytearray | None:
        """Build on-power behavior command."""
        if isinstance(value, str):
            mode = self.int_if_str_in(value, SP541E_ON_POWER, channel.status.on_power)
        else:
            mode = int(value)
        if mode not in SP541E_ON_POWER:
            return None
        return self._encode(0x0B, bytearray([mode]))

    def fetch_on_power_list(
        self, device: UniledNetDevice, channel: UniledChannel
    ) -> list | None:
        """Return on-power behavior options."""
        return list(SP541E_ON_POWER.values())

    @staticmethod
    def _encode(cmd: int, payload: bytearray, key: int = SP541E_DEFAULT_KEY) -> bytearray:
        """Encode a BanlanX network command packet."""
        size = len(payload)
        packet = bytearray(SP541E_HEADER)
        packet.extend(
            [
                cmd & 0xFF,
                key & 0xFF,
                0x00,  # total packets for network mode
                0x00,  # packet number for network mode
            ]
        )
        packet.extend(size.to_bytes(2, byteorder="big"))
        packet.extend(payload)
        return packet

    @staticmethod
    def _is_color_mode(channel: UniledChannel) -> bool:
        """Return whether channel currently targets color brightness."""
        mode = channel.status.light_mode_number
        return mode in (MODE_STATIC_COLOR, MODE_DYNAMIC_COLOR, MODE_SOUND_COLOR, MODE_CUSTOM_COLOR)


SP541E = BanlanXSP541ENet(
    model_num=0x541E,
    model_name="SP541E",
    description="BanlanX SP541E Network Controller",
    manufacturer="SPLED (BanlanX)",
    channels=1,
)
