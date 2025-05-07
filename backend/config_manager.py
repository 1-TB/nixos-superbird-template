import json
import logging # Use standard logging
import os
import threading

# Use the logger configured in main_gui_app.py or a specific one
logger = logging.getLogger("ConfigManager") # Changed from "ConfigManager"

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = {}
        self.lock = threading.Lock() # Prevent race conditions when reading/writing
        self.load_config()

    def _get_default_config(self):
        # Define default mappings - USE KEY NAMES from keycodes.py!
        # These actions should correspond to what input_handler.py can detect
        return {
            "knob_cw": {"type": "key_tap", "keys": ["VOLUME_UP"]},
            "knob_ccw": {"type": "key_tap", "keys": ["VOLUME_DOWN"]},
            "front_button_press": {"type": "key_press", "keys": ["LEFT_CTRL"]}, # Example: Just Ctrl press
            "front_button_release": {"type": "key_release", "keys": ["LEFT_CTRL"]}, # Example: Ctrl release
            "top_button_1_press": {"type": "key_tap", "keys": ["A"]},
            "top_button_1_release": {"type": "none"}, # Default no action on release
            "top_button_2_press": {"type": "key_tap", "keys": ["B"]},
            "top_button_2_release": {"type": "none"},
            "top_button_3_press": {"type": "key_tap", "keys": ["C"]},
            "top_button_3_release": {"type": "none"},
            "top_button_4_press": {"type": "key_tap", "keys": ["D"]},
            "top_button_4_release": {"type": "none"},
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
                            # Optional: Validate or merge with defaults to ensure all actions exist
                            default_conf = self._get_default_config()
                            for key, value in default_conf.items():
                                if key not in self.config:
                                    logger.info(f"Adding missing default action '{key}' to config.")
                                    self.config[key] = value
                            # Remove keys from loaded config that are no longer in defaults (optional)
                else:
                    logger.warning(f"Config file not found at {self.config_path}. Creating with defaults.")
                    self.config = self._get_default_config()
                    self.save_config()
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {self.config_path}. Using default config and attempting to save.")
                self.config = self._get_default_config()
                self.save_config() # Try to save a valid default config
            except Exception as e:
                logger.exception(f"Failed to load config: {e}. Using default config.")
                self.config = self._get_default_config()
        return self.config # Return a copy to prevent accidental modification of internal state

    def save_config(self):
        success = False
        with self.lock:
            try:
                # Ensure directory exists if path includes directories
                config_dir = os.path.dirname(self.config_path)
                if config_dir and not os.path.exists(config_dir):
                    os.makedirs(config_dir, exist_ok=True)
                    logger.info(f"Created directory for config file: {config_dir}")

                with open(self.config_path, 'w') as f:
                    json.dump(self.config, f, indent=4, sort_keys=True) # sort_keys for consistent output
                logger.info(f"Saved configuration to {self.config_path}")
                success = True
            except Exception as e:
                logger.exception(f"Failed to save config to {self.config_path}: {e}")
        return success

    def get_mappings(self):
        with self.lock:
            # Return a deep copy to prevent modification outside the manager affecting internal state
            return json.loads(json.dumps(self.config))

    def update_mappings(self, new_mappings):
        logger.debug(f"Attempting to update mappings with: {new_mappings}")
        if isinstance(new_mappings, dict):
             with self.lock:
                self.config = new_mappings # Assume new_mappings is the complete valid set
             return self.save_config()
        else:
            logger.error(f"Invalid data type provided for update_mappings. Expected dict, got {type(new_mappings)}.")
            return False
