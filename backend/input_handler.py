import evdev
import logging
import time
import threading
from select import select
import os # For checking device paths

# Use the logger configured in main_gui_app.py or a specific one
logger = logging.getLogger("InputHandler")

class InputHandler:
    def __init__(self, device_paths, command_queue, config_manager):
        if not isinstance(device_paths, list):
            logger.error(f"Device paths should be a list, got {type(device_paths)}. Correcting to empty list.")
            self.device_paths = []
        else:
            self.device_paths = device_paths

        self.command_queue = command_queue
        self.config_manager = config_manager
        self.devices_map = {} # Stores {fd: evdev.InputDevice}
        self.stop_event = threading.Event()
        self.mappings = {}

        # --- Event Code Definitions ---
        # YOU MUST REPLACE THESE WITH ACTUAL VALUES FROM `evtest` ON YOUR CAR THING
        # Format: list of tuples, where each tuple is (event_type, event_code, event_value)
        # These are EXAMPLES. Your device will likely have different codes.
        self.EVENT_MAPPINGS = {
            # Knob - REL_DIAL is common for rotary encoders
            "knob_cw": [(evdev.ecodes.EV_REL, evdev.ecodes.REL_DIAL, 1)],
            "knob_ccw": [(evdev.ecodes.EV_REL, evdev.ecodes.REL_DIAL, -1)],
            # Front Button - Example: using KEY_ENTER
            "front_button_press": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_ENTER, 1)], # 1 for press
            "front_button_release": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_ENTER, 0)],# 0 for release
            # Top Buttons - Examples: using KEY_1 to KEY_4
            "top_button_1_press": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_1, 1)],
            "top_button_1_release": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_1, 0)],
            "top_button_2_press": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_2, 1)],
            "top_button_2_release": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_2, 0)],
            "top_button_3_press": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_3, 1)],
            "top_button_3_release": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_3, 0)],
            "top_button_4_press": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_4, 1)],
            "top_button_4_release": [(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_4, 0)],
        }
        # Reverse map for quick lookup: {(type, code, value): action_key}
        self.EVENT_TUPLE_TO_ACTION = {
            event_tuple: action_key
            for action_key, event_tuples in self.EVENT_MAPPINGS.items()
            for event_tuple in event_tuples
        }

        self.load_mappings()

    def load_mappings(self):
        self.mappings = self.config_manager.get_mappings()
        logger.info(f"InputHandler mappings reloaded: {len(self.mappings)} actions configured.")
        logger.debug(f"Current mappings: {self.mappings}")


    def _connect_devices(self):
        # Close any existing connections before attempting to reconnect
        for fd, dev in list(self.devices_map.items()):
            try:
                logger.info(f"Closing stale connection to {dev.path}")
                dev.close()
            except Exception as e:
                logger.error(f"Error closing stale device {dev.path}: {e}")
            del self.devices_map[fd]

        if not self.device_paths:
            logger.warning("No device paths provided to InputHandler.")
            return False

        for path in self.device_paths:
            if not os.path.exists(path):
                logger.warning(f"Input device path does not exist: {path}")
                continue
            if not os.access(path, os.R_OK):
                logger.warning(f"Input device path not readable (permissions?): {path}")
                continue
            try:
                dev = evdev.InputDevice(path)
                # Grab device to ensure exclusive access if needed (be careful with this)
                # try:
                #     dev.grab() # This can prevent other applications (like desktop environment) from seeing events
                #     logger.info(f"Grabbed device: {dev.name} ({path})")
                # except IOError as e:
                #     logger.warning(f"Could not grab device {dev.name}: {e}. It might be in use or permissions issue.")

                self.devices_map[dev.fd] = dev
                logger.info(f"Successfully connected to input device: {dev.name} ({path}), fd: {dev.fd}")
                logger.info(f"Device capabilities: {dev.capabilities(verbose=True)}")
            except Exception as e:
                logger.error(f"Failed to connect to input device {path}: {e}")
        return bool(self.devices_map)

    def run(self):
        logger.info("Input Handler starting...")
        if not self._connect_devices():
            logger.warning("Initial connection to input devices failed. Will retry.")

        while not self.stop_event.is_set():
            if not self.devices_map:
                logger.warning("No input devices connected. Retrying connection in 5 seconds...")
                time.sleep(5)
                if not self._connect_devices():
                    continue # Skip to next loop iteration if still no devices

            try:
                fds_to_watch = list(self.devices_map.keys())
                if not fds_to_watch: # Should be caught by the self.devices_map check above
                    time.sleep(1)
                    continue

                # select() call: arguments are (read_fds, write_fds, error_fds, timeout_in_seconds)
                r, w, x = select(fds_to_watch, [], fds_to_watch, 1.0) # Timeout 1 second

                if self.stop_event.is_set(): break

                for fd in r: # Readable file descriptors
                    device = self.devices_map.get(fd)
                    if not device: continue # Should not happen if fds_to_watch is from keys

                    try:
                        for event in device.read():
                            self.process_event(event, device.path)
                    except BlockingIOError:
                        # No events available to read (shouldn't happen often with select)
                        pass
                    except OSError as e: # This can happen if device is disconnected
                        logger.error(f"OSError reading from device {device.path} (fd {fd}): {e}. Disconnecting device.")
                        device.close()
                        del self.devices_map[fd]
                        # No need to explicitly reconnect here, the loop will try if devices_map becomes empty
                        break # Break from processing events for this device

                for fd in x: # File descriptors with errors
                     device = self.devices_map.get(fd)
                     logger.error(f"Error on file descriptor for device {device.path if device else fd}. Disconnecting.")
                     if device:
                         device.close()
                         del self.devices_map[fd]


            except Exception as e:
                logger.exception(f"Unhandled error in input loop: {e}")
                # Attempt to recover: Clear all devices to force full reconnect attempt
                for dev_fd, dev_obj in list(self.devices_map.items()):
                    try: dev_obj.close()
                    except: pass
                self.devices_map.clear()
                time.sleep(5) # Wait a bit before retrying full connection

        logger.info("Input Handler stopping...")
        for fd, dev in self.devices_map.items():
            try:
                # dev.ungrab() # If grabbed
                dev.close()
                logger.info(f"Closed device {dev.path}")
            except Exception as e:
                logger.error(f"Error closing device {dev.path}: {e}")
        self.devices_map.clear()
        logger.info("Input Handler stopped.")


    def stop(self):
        logger.info("Input Handler stop requested.")
        self.stop_event.set()

    def process_event(self, event, device_path):
        # logger.debug(f"Raw event from {device_path}: type={event.type}, code={event.code}, value={event.value}, sec={event.sec}, usec={event.usec}")

        if event.type == evdev.ecodes.EV_SYN:
            # SYN_REPORT indicates end of a packet of events.
            # For simple key/knob events, often not needed for logic unless dealing with complex sequences.
            # logger.debug(f"Sync event from {device_path}: SYN_REPORT code={event.code} value={event.value}")
            return

        event_tuple = (event.type, event.code, event.value)
        # logger.debug(f"Processed event tuple: {event_tuple} from {device_path}")

        action_key = self.EVENT_TUPLE_TO_ACTION.get(event_tuple)

        if action_key:
            logger.info(f"Detected action: '{action_key}' from device {device_path} (event: {event_tuple})")
            if action_key in self.mappings:
                command_config = self.mappings[action_key]
                logger.debug(f"Mapping found for '{action_key}': {command_config}")

                command_type = command_config.get("type")
                keys_to_act = command_config.get("keys", [])

                if not keys_to_act and command_type != "none": # "none" type doesn't need keys
                    logger.warning(f"No keys defined for action '{action_key}' with type '{command_type}'. Skipping.")
                    return

                if command_type == "key_press":
                    self.command_queue.put({'type': 'press', 'keys': keys_to_act})
                elif command_type == "key_release":
                     self.command_queue.put({'type': 'release', 'keys': keys_to_act})
                elif command_type == "key_tap":
                     self.command_queue.put({'type': 'press', 'keys': keys_to_act})
                     # A very small delay might be necessary for some OS/apps to register tap correctly
                     # However, HID service usually sends release immediately after press for tap.
                     # Forcing a slight delay here if problems arise:
                     # time.sleep(0.01) # 10ms, use with caution, can block this handler
                     self.command_queue.put({'type': 'release', 'keys': keys_to_act})
                elif command_type == "none":
                    logger.debug(f"Action '{action_key}' is configured to 'none'. No command sent.")
                else:
                    logger.warning(f"Unknown command type '{command_type}' for action '{action_key}'")
            else:
                 logger.warning(f"No mapping defined in config file for detected action: '{action_key}'")
        # else:
            # logger.debug(f"No action key defined for event tuple: {event_tuple}")
