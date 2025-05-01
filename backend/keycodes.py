# Source/Inspiration: https://github.com/micropython/micropython/blob/master/drivers/bluetooth/ble_hid_keyboard.py
# And Linux input event codes: /usr/include/linux/input-event-codes.h

class KeycodeMap:
    """Maps key names to HID Usage IDs and Modifier masks."""
    def __init__(self):
        # Modifier masks (byte 0)
        self.MOD_NONE = 0x00
        self.MOD_LEFT_CTRL = 0x01
        self.MOD_LEFT_SHIFT = 0x02
        self.MOD_LEFT_ALT = 0x04
        self.MOD_LEFT_GUI = 0x08  # Windows/Command Key
        self.MOD_RIGHT_CTRL = 0x10
        self.MOD_RIGHT_SHIFT = 0x20
        self.MOD_RIGHT_ALT = 0x40 # AltGr
        self.MOD_RIGHT_GUI = 0x80

        # HID Usage IDs (bytes 2-7)
        self.NAME_TO_CODE = {
            # Letters
            "A": (self.MOD_NONE, 0x04), "B": (self.MOD_NONE, 0x05), "C": (self.MOD_NONE, 0x06),
            "D": (self.MOD_NONE, 0x07), "E": (self.MOD_NONE, 0x08), "F": (self.MOD_NONE, 0x09),
            "G": (self.MOD_NONE, 0x0A), "H": (self.MOD_NONE, 0x0B), "I": (self.MOD_NONE, 0x0C),
            "J": (self.MOD_NONE, 0x0D), "K": (self.MOD_NONE, 0x0E), "L": (self.MOD_NONE, 0x0F),
            "M": (self.MOD_NONE, 0x10), "N": (self.MOD_NONE, 0x11), "O": (self.MOD_NONE, 0x12),
            "P": (self.MOD_NONE, 0x13), "Q": (self.MOD_NONE, 0x14), "R": (self.MOD_NONE, 0x15),
            "S": (self.MOD_NONE, 0x16), "T": (self.MOD_NONE, 0x17), "U": (self.MOD_NONE, 0x18),
            "V": (self.MOD_NONE, 0x19), "W": (self.MOD_NONE, 0x1A), "X": (self.MOD_NONE, 0x1B),
            "Y": (self.MOD_NONE, 0x1C), "Z": (self.MOD_NONE, 0x1D),
            # Numbers
            "1": (self.MOD_NONE, 0x1E), "2": (self.MOD_NONE, 0x1F), "3": (self.MOD_NONE, 0x20),
            "4": (self.MOD_NONE, 0x21), "5": (self.MOD_NONE, 0x22), "6": (self.MOD_NONE, 0x23),
            "7": (self.MOD_NONE, 0x24), "8": (self.MOD_NONE, 0x25), "9": (self.MOD_NONE, 0x26),
            "0": (self.MOD_NONE, 0x27),
            # Punctuation & Symbols
            "ENTER": (self.MOD_NONE, 0x28), "ESCAPE": (self.MOD_NONE, 0x29), "BACKSPACE": (self.MOD_NONE, 0x2A),
            "TAB": (self.MOD_NONE, 0x2B), "SPACE": (self.MOD_NONE, 0x2C),
            "MINUS": (self.MOD_NONE, 0x2D), "EQUAL": (self.MOD_NONE, 0x2E),
            "LEFT_BRACKET": (self.MOD_NONE, 0x2F), "RIGHT_BRACKET": (self.MOD_NONE, 0x30),
            "BACKSLASH": (self.MOD_NONE, 0x31), "HASH": (self.MOD_NONE, 0x32), # Varies by layout (#~)
            "SEMICOLON": (self.MOD_NONE, 0x33), "QUOTE": (self.MOD_NONE, 0x34), # Apostrophe
            "GRAVE": (self.MOD_NONE, 0x35), # Backtick `~`
            "COMMA": (self.MOD_NONE, 0x36), "PERIOD": (self.MOD_NONE, 0x37), "SLASH": (self.MOD_NONE, 0x38),
            # Function Keys
            "F1": (self.MOD_NONE, 0x3A), "F2": (self.MOD_NONE, 0x3B), "F3": (self.MOD_NONE, 0x3C),
            "F4": (self.MOD_NONE, 0x3D), "F5": (self.MOD_NONE, 0x3E), "F6": (self.MOD_NONE, 0x3F),
            "F7": (self.MOD_NONE, 0x40), "F8": (self.MOD_NONE, 0x41), "F9": (self.MOD_NONE, 0x42),
            "F10": (self.MOD_NONE, 0x43), "F11": (self.MOD_NONE, 0x44), "F12": (self.MOD_NONE, 0x45),
            # Control Keys
            "CAPS_LOCK": (self.MOD_NONE, 0x39), "PRINT_SCREEN": (self.MOD_NONE, 0x46),
            "SCROLL_LOCK": (self.MOD_NONE, 0x47), "PAUSE": (self.MOD_NONE, 0x48),
            "INSERT": (self.MOD_NONE, 0x49), "HOME": (self.MOD_NONE, 0x4A), "PAGE_UP": (self.MOD_NONE, 0x4B),
            "DELETE": (self.MOD_NONE, 0x4C), "END": (self.MOD_NONE, 0x4D), "PAGE_DOWN": (self.MOD_NONE, 0x4E),
            "RIGHT_ARROW": (self.MOD_NONE, 0x4F), "LEFT_ARROW": (self.MOD_NONE, 0x50),
            "DOWN_ARROW": (self.MOD_NONE, 0x51), "UP_ARROW": (self.MOD_NONE, 0x52),
            # Keypad
            "KP_NUMLOCK": (self.MOD_NONE, 0x53), "KP_SLASH": (self.MOD_NONE, 0x54),
            "KP_ASTERISK": (self.MOD_NONE, 0x55), "KP_MINUS": (self.MOD_NONE, 0x56),
            "KP_PLUS": (self.MOD_NONE, 0x57), "KP_ENTER": (self.MOD_NONE, 0x58),
            "KP_1": (self.MOD_NONE, 0x59), "KP_2": (self.MOD_NONE, 0x5A), "KP_3": (self.MOD_NONE, 0x5B),
            "KP_4": (self.MOD_NONE, 0x5C), "KP_5": (self.MOD_NONE, 0x5D), "KP_6": (self.MOD_NONE, 0x5E),
            "KP_7": (self.MOD_NONE, 0x5F), "KP_8": (self.MOD_NONE, 0x60), "KP_9": (self.MOD_NONE, 0x61),
            "KP_0": (self.MOD_NONE, 0x62), "KP_PERIOD": (self.MOD_NONE, 0x63),
            # Modifiers (represent these as separate keys if needed, or use MOD flags)
            "LEFT_CTRL": (self.MOD_LEFT_CTRL, 0x00), "LEFT_SHIFT": (self.MOD_LEFT_SHIFT, 0x00),
            "LEFT_ALT": (self.MOD_LEFT_ALT, 0x00), "LEFT_GUI": (self.MOD_LEFT_GUI, 0x00),
            "RIGHT_CTRL": (self.MOD_RIGHT_CTRL, 0x00), "RIGHT_SHIFT": (self.MOD_RIGHT_SHIFT, 0x00),
            "RIGHT_ALT": (self.MOD_RIGHT_ALT, 0x00), "RIGHT_GUI": (self.MOD_RIGHT_GUI, 0x00),
            # Media Keys (Consumer Page 0x0C) - Need different report structure usually
            # For simplicity, map to common F-key equivalents if possible, or implement consumer report
            "VOLUME_UP": (self.MOD_NONE, 0x80), # Usage ID 0xE9 from consumer page (map to F key or implement consumer report)
            "VOLUME_DOWN": (self.MOD_NONE, 0x81), # Usage ID 0xEA from consumer page (map to F key or implement consumer report)
            "MUTE": (self.MOD_NONE, 0x7F), # Usage ID 0xE2
            "PLAY_PAUSE": (self.MOD_NONE, 0xCD), # Usage ID 0xCD
            "NEXT_TRACK": (self.MOD_NONE, 0xB5), # Usage ID 0xB5
            "PREV_TRACK": (self.MOD_NONE, 0xB6), # Usage ID 0xB6
            "STOP_MEDIA": (self.MOD_NONE, 0xB7), # Usage ID 0xB7
            # Placeholder for None/Empty Action
            "NONE": (self.MOD_NONE, 0x00),
        }

        # Map Usage ID back to name if needed (e.g., for display)
        self.CODE_TO_NAME = {v[1]: k for k, v in self.NAME_TO_CODE.items() if v[1] != 0x00}
        # Add modifiers separately if needed for display
        self.CODE_TO_NAME[0xE0] = "LEFT_CTRL" # Approx mapping
        self.CODE_TO_NAME[0xE1] = "LEFT_SHIFT"
        # ...

    def get_codes(self, key_name):
        """Returns (modifier_mask, key_code) tuple for a given key name."""
        key_name_upper = key_name.upper()
        return self.NAME_TO_CODE.get(key_name_upper, (self.MOD_NONE, 0x00)) # Return None/0x00 if not found

    def get_name(self, key_code):
        """Returns key name for a given HID Usage ID (key code part)."""
        # Note: This doesn't handle modifiers easily from code alone
        return self.CODE_TO_NAME.get(key_code, "UNKNOWN")