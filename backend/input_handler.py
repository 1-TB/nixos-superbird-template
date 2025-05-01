import evdev
import logging
import time
import threading
from select import select

logger = logging.getLogger("InputHandler")

class InputHandler:
    def __init__(self, device_paths, command_queue, config_manager):
        self.device_paths = device_paths
        self.command_queue = command_queue
        self.config_manager = config_manager
        self.devices = {}
        self.stop_event = threading.Event()
        self.mappings = {} # Loaded from config_manager

        # --- Placeholder Event Codes/Values ---
        # You MUST replace these with actual values from `evtest`
        self.KNOB_TURN_CLOCKWISE_EVENTS = [(evdev.ecodes.EV_REL, evdev.ecodes.REL_DIAL, 1)] # Example
        self.KNOB_TURN_COUNTER_CLOCKWISE_EVENTS = [(evdev.ecodes.EV_REL, evdev.ecodes.REL_DIAL, -1)] # Example
        self.FRONT_BUTTON_PRESS_EVENTS = [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_ENTER, 1)] # Example: Button press is 'Enter' keycode=1
        self.FRONT_BUTTON_RELEASE_EVENTS = [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_ENTER, 0)] # Example: Button release is 'Enter' keycode=0
        # Add similar definitions for the 4 top buttons
        self.TOP_BUTTON_1_PRESS_EVENTS = [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_1, 1)] # Example
        self.TOP_BUTTON_1_RELEASE_EVENTS = [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_1, 0)] # Example
        # ... define for TOP_BUTTON_2, 3, 4 ...

        self.load_mappings()

    def load_mappings(self):
        self.mappings = self.config_manager.get_mappings()
        logger.info(f"Loaded mappings: {self.mappings}")

    def _connect_devices(self):
        self.devices = {}
        for path in self.device_paths:
            try:
                dev = evdev.InputDevice(path)
                self.devices[dev.fd] = dev
                logger.info(f"Successfully connected to input device: {dev.name} ({path})")
            except Exception as e:
                logger.error(f"Failed to connect to input device {path}: {e}")
        return bool(self.devices) # Return True if at least one device connected

    def run(self):
        logger.info("Input Handler starting...")
        while not self.stop_event.is_set():
            if not self.devices:
                logger.warning("No input devices connected. Retrying connection in 5 seconds...")
                if not self._connect_devices():
                    time.sleep(5)
                    continue # Skip to next loop iteration if still no devices

            try:
                # Watch device file descriptors for events
                fds = list(self.devices.keys())
                r, w, x = select(fds, [], [], 1) # Timeout 1 second

                for fd in r:
                    device = self.devices[fd]
                    try:
                        for event in device.read():
                            self.process_event(event, device.path)
                    except BlockingIOError:
                        # No events available to read (shouldn't happen often with select)
                        pass
                    except OSError as e:
                        logger.error(f"Error reading from device {device.path}: {e}. Disconnecting.")
                        del self.devices[fd] # Remove problematic device
                        device.close()
                        # Attempt reconnect on next loop cycle

            except Exception as e:
                logger.exception(f"Error in input loop: {e}")
                # Attempt to recover or wait before retrying
                self.devices = {} # Clear devices to force reconnect attempt
                time.sleep(5)

        logger.info("Input Handler stopping...")
        for fd, dev in self.devices.items():
            try:
                dev.close()
            except Exception as e:
                logger.error(f"Error closing device {dev.path}: {e}")

    def stop(self):
        self.stop_event.set()

    def process_event(self, event, device_path):
        # Optional: Log raw events for debugging
        # logger.debug(f"Raw event from {device_path}: type={event.type}, code={event.code}, value={event.value}")

        # Ignore synchronization events for basic mapping
        if event.type == evdev.ecodes.EV_SYN:
            return

        # Create a tuple representing the event for easy comparison
        event_tuple = (event.type, event.code, event.value)
        logger.debug(f"Processed event tuple: {event_tuple}")

        action_key = None

        # --- Match Event Tuples to Action Keys (NEEDS CUSTOMIZATION) ---
        if event_tuple in self.KNOB_TURN_CLOCKWISE_EVENTS:
            action_key = "knob_cw"
        elif event_tuple in self.KNOB_TURN_COUNTER_CLOCKWISE_EVENTS:
            action_key = "knob_ccw"
        elif event_tuple in self.FRONT_BUTTON_PRESS_EVENTS:
            action_key = "front_button_press"
        elif event_tuple in self.FRONT_BUTTON_RELEASE_EVENTS:
             action_key = "front_button_release" # Needed if mapping release actions
        elif event_tuple in self.TOP_BUTTON_1_PRESS_EVENTS:
            action_key = "top_button_1_press"
        elif event_tuple in self.TOP_BUTTON_1_RELEASE_EVENTS:
            action_key = "top_button_1_release"
        # ... add elif for other top buttons ...

        # --- Handle Action ---
        if action_key:
            logger.info(f"Detected action: {action_key}")
            if action_key in self.mappings:
                command_config = self.mappings[action_key]
                logger.info(f"Mapping found for {action_key}: {command_config}")

                command_type = command_config.get("type")
                keys = command_config.get("keys", [])

                if command_type == "key_press":
                    # Send press command for listed keys
                    self.command_queue.put({'type': 'press', 'keys': keys})
                elif command_type == "key_release":
                     # Send release command for listed keys
                     self.command_queue.put({'type': 'release', 'keys': keys})
                elif command_type == "key_tap": # Press then immediately release
                     self.command_queue.put({'type': 'press', 'keys': keys})
                     # Small delay might be needed depending on host OS responsiveness
                     # time.sleep(0.01)
                     self.command_queue.put({'type': 'release', 'keys': keys})
                else:
                    logger.warning(f"Unknown command type '{command_type}' for action '{action_key}'")
            else:
                 logger.warning(f"No mapping defined for action: {action_key}")