import json
import logging
import os
import threading

logger = logging.getLogger("ConfigManager")

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = {}
        self.lock = threading.Lock() # Prevent race conditions when reading/writing
        self.load_config()

    def _get_default_config(self):
        # Define default mappings - USE KEY NAMES from keycodes.py!
        return {
            "knob_cw": {"type": "key_tap", "keys": ["VOLUME_UP"]},
            "knob_ccw": {"type": "key_tap", "keys": ["VOLUME_DOWN"]},
            "front_button_press": {"type": "key_press", "keys": ["LEFT_CTRL", "C"]}, # Example: Ctrl+C
            "front_button_release": {"type": "key_release", "keys": ["LEFT_CTRL", "C"]},
            "top_button_1_press": {"type": "key_tap", "keys": ["A"]},
            "top_button_1_release": {"type": "none"}, # Default no action on release
            "top_button_2_press": {"type": "key_tap", "keys": ["B"]},
            "top_button_2_release": {"type": "none"},
            "top_button_3_press": {"type": "key_tap", "keys": ["C"]},
            "top_button_3_release": {"type": "none"},
            "top_button_4_press": {"type": "key_tap", "keys": ["D"]},
            "top_button_4_release": {"type": "none"},
            # Add keys for touchscreen events if desired
            # "touch_tap_area1": {"type": "key_tap", "keys": ["F1"]},
        }

    def load_config(self):
        with self.lock:
            try:
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r') as f:
                        content = f.read()
                        if not content: # Handle empty file case
                            logger.warning(f"Config file {self.config_path} is empty, using defaults.")
                            self.config = self._get_default_config()
                            self.save_config() # Save defaults back to file
                        else:
                            self.config = json.loads(content)
                            logger.info(f"Loaded configuration from {self.config_path}")
                            # Optional: Validate loaded config against defaults/schema here
                else:
                    logger.warning(f"Config file not found at {self.config_path}. Creating with defaults.")
                    self.config = self._get_default_config()
                    self.save_config()
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {self.config_path}. Using default config.")
                self.config = self._get_default_config()
            except Exception as e:
                logger.exception(f"Failed to load config: {e}. Using default config.")
                self.config = self._get_default_config()
        return self.config

    def save_config(self):
        with self.lock:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w') as f:
                    json.dump(self.config, f, indent=4)
                logger.info(f"Saved configuration to {self.config_path}")
                return True
            except Exception as e:
                logger.exception(f"Failed to save config: {e}")
                return False

    def get_mappings(self):
        with self.lock:
            # Return a copy to prevent modification outside the manager
            return self.config.copy()

    def update_mappings(self, new_mappings):
        logger.info(f"Updating mappings with: {new_mappings}")
        # Basic validation - could be more extensive
        if isinstance(new_mappings, dict):
             with self.lock:
                self.config = new_mappings
             return self.save_config()
        else:
            logger.error("Invalid data type provided for update_mappings. Expected dict.")
            return False