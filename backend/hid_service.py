import dbus
import dbus.service
import dbus.mainloop.glib
import logging
import time
import threading
from gi.repository import GLib, GObject # Use GObject main loop for D-Bus
import os # For os.write, os.read, os.close

# Import keycodes
from .keycodes import KeycodeMap # Relative import within package

# Use the logger configured in main_gui_app.py or a specific one
logger = logging.getLogger("HidService")

# --- D-Bus Constants (BlueZ HID Profile) ---
BLUEZ_SERVICE_NAME = 'org.bluez'
ADAPTER_INTERFACE = 'org.bluez.Adapter1'
DEVICE_INTERFACE = 'org.bluez.Device1'
PROFILE_MANAGER_INTERFACE = 'org.bluez.ProfileManager1'
# HID_PROFILE_INTERFACE = 'org.bluez.HidProfile1' # This is what we implement, not a standard BlueZ one.
HID_DBUS_PATH = '/org/example/bluez/custom_hid_profile' # Custom path for our profile registration

# Standard HID Keyboard Report Descriptor (simplified)
# This one includes 1 report ID for keyboard.
# Report ID (1) - Keyboard
#   Byte 0: Modifier Keys (Bitmask: LCtrl, LShift, LAlt, LGui, RCtrl, RShift, RAlt, RGui)
#   Byte 1: Reserved (0x00)
#   Byte 2-7: Keycodes (Rollover of 6 keys)
# (This is a common descriptor. Ensure it matches the capabilities you want to advertise)
SDP_RECORD_XML_TEMPLATE = """
<?xml version="1.0" encoding="UTF-8" ?>
<record>
  <attribute id="0x0001"> <sequence> <uuid value="0x1124" /> </sequence> </attribute>
  <attribute id="0x0004"> <sequence>
      <sequence> <uuid value="0x0100" /> <uint16 value="0x0011" /> </sequence> <sequence> <uuid value="0x0011" /> </sequence> </sequence>
  </attribute>
  <attribute id="0x0005"> <sequence> <uuid value="0x1002" /> </sequence> </attribute>
  <attribute id="0x0006"> <sequence> <uint16 value="0x656e" /> <uint16 value="0x006a" /> <uint16 value="0x0100" /> </sequence> </attribute>
  <attribute id="0x0009"> <sequence> <sequence> <uuid value="0x1124" /> <uint16 value="0x0101" /> </sequence> </sequence> </attribute>
  <attribute id="0x0100"> <text value="{service_name}" /> </attribute>
  <attribute id="0x0101"> <text value="Bluetooth HID MacroPad" /> </attribute>
  <attribute id="0x0102"> <text value="NixOS-Superbird" /> </attribute>

  <attribute id="0x0201"> <uint16 value="0x0111" /> </attribute> <attribute id="0x0202"> <uint8 value="0x00" /> </attribute> <attribute id="0x0203"> <uint8 value="0x01" /> </attribute> <attribute id="0x0204"> <boolean value="true" /> </attribute> <attribute id="0x0205"> <boolean value="true" /> </attribute> <attribute id="0x0206"> <sequence><sequence>
        <uint8 value="0x22" /> <text value="05010906A101050719E029E71500250175019508810205071900296515002565750895068100050819012905750195059102750395019103C0" />
        </sequence></sequence>
  </attribute>
  <attribute id="0x0207"> <sequence><sequence> <uint16 value="0x0409" /> <uint16 value="0x0100" /> </sequence></sequence> </attribute> <attribute id="0x020B"> <boolean value="false" /> </attribute> <attribute id="0x020E"> <boolean value="true" /> </attribute> </record>
"""


class HidProfile(dbus.service.Object):
    """
    Custom BlueZ HID Profile implementation.
    Handles connection requests and provides communication channels.
    """
    def __init__(self, bus, path, hid_service_ref):
        super().__init__(bus, path)
        self.hid_service = hid_service_ref # Weak reference or direct reference
        self.device_path = None # Object path of the connected host device
        self.interrupt_fd = -1
        self.interrupt_io_watch_id = 0
        self.control_fd = -1 # Not typically used for basic keyboard output
        logger.info(f"HidProfile instance created at D-Bus path: {path}")

    @dbus.service.method(PROFILE_MANAGER_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        logger.info(f"HID Profile Release called by BlueZ for {self.object_path}")
        # This is called when the profile is unregistered.
        # self.hid_service might initiate this on shutdown.
        # Or BlueZ might call this if it's shutting down.

    @dbus.service.method(PROFILE_MANAGER_INTERFACE, in_signature="o{sv}", out_signature="")
    def NewConnection(self, device_path, fd_dict):
        self.device_path = device_path
        logger.info(f"New HID Connection from host device: {device_path}")
        try:
            # device_obj = self.hid_service.bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            # self.device_interface = dbus.Interface(device_obj, DEVICE_INTERFACE)
            # logger.info(f"Device properties: {self.device_interface.GetAll(DEVICE_INTERFACE)}")

            self.interrupt_fd = fd_dict['fd'].take() # take() transfers ownership of the FD
            logger.info(f"Interrupt channel FD {self.interrupt_fd} obtained for device {device_path}.")

            # Add FD to GObject main loop for monitoring
            # IO_IN for reading (e.g. LED status from host), IO_HUP/ERR for disconnects
            self.interrupt_io_watch_id = GObject.io_add_watch(
                self.interrupt_fd,
                GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
                self.interrupt_channel_event_cb
            )
            logger.info(f"Watching interrupt channel FD {self.interrupt_fd} (watch_id: {self.interrupt_io_watch_id}).")

            # Store this connection profile in the parent HidService
            self.hid_service.register_active_connection(self)

        except Exception as e:
            logger.exception(f"Error setting up new HID connection for {device_path}: {e}")
            if self.interrupt_fd != -1:
                try: os.close(self.interrupt_fd)
                except: pass
                self.interrupt_fd = -1
            # Potentially signal HidService to remove this failed profile instance or retry.

    @dbus.service.method(PROFILE_MANAGER_INTERFACE, in_signature="o", out_signature="")
    def RequestDisconnection(self, device_path):
        logger.warning(f"HID Disconnection requested by BlueZ for device: {device_path}")
        if self.device_path == device_path:
            self.cleanup_connection_resources()
            # HidService will be notified via unregister_active_connection
        else:
             logger.warning(f"Disconnection request for non-matching device. Current: {self.device_path}, Requested: {device_path}")

    def interrupt_channel_event_cb(self, fd, conditions):
        """Callback when data is available or connection closed on interrupt channel."""
        if fd != self.interrupt_fd:
            logger.error(f"Callback for unexpected fd {fd}, expecting {self.interrupt_fd}")
            return False # Remove watch

        if conditions & (GLib.IO_HUP | GLib.IO_ERR):
            logger.warning(f"Interrupt channel (fd {fd}, device {self.device_path}) closed or error (HUP/ERR). Conditions: {conditions}")
            self.cleanup_connection_resources()
            return False # Remove watch, GObject.io_add_watch will do this automatically

        if conditions & GLib.IO_IN:
            try:
                # Read data received from host (e.g., LED status updates for CapsLock, NumLock)
                data = os.read(fd, 1024) # Max buffer size
                if not data: # Empty read can also mean channel closed
                    logger.warning(f"Empty read on interrupt channel (fd {fd}), treating as HUP.")
                    self.cleanup_connection_resources()
                    return False # Remove watch
                logger.debug(f"Received data on interrupt channel (fd {fd}): {data.hex()}")
                # Handle SET_REPORT for LED status if your descriptor supports it
                # Example: if data[0] == 0xa2 (HIDP_TRANS_DATA | HIDP_DATA_RTYPE_OUTPUT) for output report
                # and data[1] is the report ID (if any, often not for simple LED).
                # data[1] (or data[0] if no report ID) would contain LED state byte.
                # self.hid_service.handle_led_update(data)
            except OSError as e:
                logger.error(f"OSError reading interrupt channel (fd {fd}): {e}")
                self.cleanup_connection_resources()
                return False # Remove watch
            except Exception as e:
                logger.exception(f"Unhandled error reading interrupt channel (fd {fd}): {e}")
                self.cleanup_connection_resources()
                return False

        return True # Keep watch active if no fatal error or HUP/ERR

    def send_report(self, report_bytes):
        """Sends a HID report over the interrupt channel."""
        if self.interrupt_fd != -1:
            try:
                bytes_written = os.write(self.interrupt_fd, report_bytes)
                logger.debug(f"Sent report ({bytes_written} bytes): {report_bytes.hex()}")
                return True
            except OSError as e: # Can happen if host disconnects abruptly
                logger.error(f"OSError sending report on fd {self.interrupt_fd} (device {self.device_path}): {e}")
                self.cleanup_connection_resources() # Connection is likely dead
            except Exception as e:
                logger.exception(f"Unhandled error sending report on fd {self.interrupt_fd}: {e}")
                self.cleanup_connection_resources()
        else:
            logger.warning(f"Cannot send report: No active interrupt channel for device {self.device_path}.")
        return False

    def cleanup_connection_resources(self):
        logger.info(f"Cleaning up HID connection resources for device {self.device_path} (fd: {self.interrupt_fd}).")
        if self.interrupt_io_watch_id > 0:
            GObject.source_remove(self.interrupt_io_watch_id)
            self.interrupt_io_watch_id = 0
            logger.debug(f"Removed IO watch for fd {self.interrupt_fd}.")

        if self.interrupt_fd != -1:
            try:
                os.close(self.interrupt_fd)
                logger.info(f"Closed interrupt channel FD {self.interrupt_fd} for {self.device_path}.")
            except OSError as e:
                logger.error(f"Error closing interrupt channel FD {self.interrupt_fd}: {e}")
            self.interrupt_fd = -1

        # Inform HidService that this connection is gone
        if self.hid_service: # Check if hid_service reference is still valid
            self.hid_service.unregister_active_connection(self)
        self.device_path = None # Clear device path

    def get_device_path(self):
        return self.device_path


class HidService:
    """Manages BlueZ D-Bus interaction, HID profile registration, and report sending."""
    def __init__(self, command_queue_ref):
        self.command_queue = command_queue_ref
        self.bus = None
        self.profile_instance = None # The D-Bus object for our profile
        self.adapter_path = None
        self.adapter_interface = None
        self.mainloop = None # GObject/GLib MainLoop
        self.stop_requested_event = threading.Event()
        self.active_connection_profile = None # Stores the HidProfile instance for the currently connected host
        self.keycode_map = KeycodeMap()
        self.bt_device_name = "NixMacroPad" # Default, can be overridden

        # Keyboard report state [Modifier, Reserved, Key1, Key2, Key3, Key4, Key5, Key6]
        # This matches the typical 8-byte HID keyboard report.
        self.report_state = bytearray([0x00] * 8)
        self.last_sent_report_state = bytearray([0x00] * 8) # To send only on change

        self._dbus_registration_id = 0 # For profile registration tracking

    def _init_dbus_and_mainloop(self):
        """Initializes D-Bus connection and main loop in the current thread."""
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True) # Use GLib's main loop for D-Bus
        self.bus = dbus.SystemBus()
        self.mainloop = GObject.MainLoop() # GLib's main loop
        logger.info("D-Bus SystemBus and GLib MainLoop initialized.")
        return True

    def _find_adapter(self):
         """Finds the first available Bluetooth adapter."""
         om = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, '/'), 'org.freedesktop.DBus.ObjectManager')
         objects = om.GetManagedObjects()
         for path, interfaces in objects.items():
             if ADAPTER_INTERFACE in interfaces:
                 self.adapter_path = path
                 self.adapter_interface = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, path), ADAPTER_INTERFACE)
                 logger.info(f"Found Bluetooth adapter: {path}")
                 return True
         logger.error("Could not find a Bluetooth adapter.")
         return False

    def _set_adapter_properties(self, device_name="NixMacroPad"):
        """Sets the adapter to be discoverable, pairable, and sets its alias."""
        self.bt_device_name = device_name
        if not self.adapter_interface:
            logger.error("Adapter not available to set properties.")
            return False
        try:
            props = dbus.Interface(self.adapter_interface, 'org.freedesktop.DBus.Properties')
            props.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(True))
            logger.info("Adapter Powered: On")
            props.Set(ADAPTER_INTERFACE, "Discoverable", dbus.Boolean(True))
            logger.info("Adapter Discoverable: On")
            props.Set(ADAPTER_INTERFACE, "Pairable", dbus.Boolean(True))
            logger.info("Adapter Pairable: On")
            props.Set(ADAPTER_INTERFACE, "Alias", dbus.String(self.bt_device_name)) # This is the name shown to other devices
            logger.info(f"Adapter Alias set to: {self.bt_device_name}")
            return True
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to set adapter properties: {e}")
            return False

    def _register_hid_profile(self):
        """Registers the custom HID profile with BlueZ."""
        try:
            profile_manager = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE_NAME, '/org/bluez'), # Standard path for ProfileManager1
                PROFILE_MANAGER_INTERFACE
            )

            # Instantiate our D-Bus service object (the profile)
            # Pass a reference to self (HidService) so the profile can call back
            self.profile_instance = HidProfile(self.bus, HID_DBUS_PATH, self)

            # Profile options
            # UUID for HID: 00001124-0000-1000-8000-00805f9b34fb
            profile_uuid = "00001124-0000-1000-8000-00805f9b34fb"
            opts = {
                "Name": dbus.String(self.bt_device_name + " Profile"), # Profile name in BlueZ (internal)
                "ServiceRecord": dbus.String(SDP_RECORD_XML_TEMPLATE.format(service_name=self.bt_device_name)),
                "Role": dbus.String("server"), # We are the HID device (server role)
                "RequireAuthentication": dbus.Boolean(False), # Simpler pairing
                "RequireAuthorization": dbus.Boolean(False),
                "AutoConnect": dbus.Boolean(True), # Allow BlueZ to auto-connect to paired hosts
                # "PSM": dbus.UInt16(0x0011), # PSM for HID Control (L2CAP_PSM_HID_CNTL), usually handled by SDP
                # "Service": profile_uuid # Redundant if SDP has it
            }
            # RegisterProfile arguments: path, UUID, options
            profile_manager.RegisterProfile(HID_DBUS_PATH, profile_uuid, opts)
            logger.info(f"HID Profile registered successfully with BlueZ at path {HID_DBUS_PATH} and UUID {profile_uuid}.")
            return True
        except dbus.exceptions.DBusException as e:
            # Common error: org.bluez.Error.AlreadyExists if path is already registered
            # org.bluez.Error.InvalidArguments if options are wrong
            logger.error(f"Failed to register HID profile: {e}")
            if "AlreadyExists" in str(e):
                 logger.info("Profile already exists. Attempting to unregister and re-register might be needed if it's stale.")
                 # You might want to try unregistering here if this happens often on restarts.
            return False
        except Exception as e:
            logger.exception(f"Unexpected error registering HID profile: {e}")
            return False


    def _unregister_hid_profile(self):
        if not self.bus or not self.profile_instance:
            logger.info("Cannot unregister profile: D-Bus or profile instance not available.")
            return
        try:
            profile_manager = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE_NAME, '/org/bluez'),
                PROFILE_MANAGER_INTERFACE
            )
            profile_manager.UnregisterProfile(HID_DBUS_PATH)
            logger.info(f"HID Profile at {HID_DBUS_PATH} unregistered successfully.")
        except dbus.exceptions.DBusException as e:
            # Common error: org.bluez.Error.DoesNotExist if it was never registered or already gone.
            if "DoesNotExist" in str(e):
                logger.info(f"Profile {HID_DBUS_PATH} was not registered or already unregistered.")
            else:
                logger.error(f"Failed to unregister HID profile {HID_DBUS_PATH}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error unregistering HID profile: {e}")
        finally:
            # Help D-Bus service object get garbage collected if it holds circular refs
            if self.profile_instance:
                # self.profile_instance.remove_from_connection() # D-Bus method if exists
                self.profile_instance = None


    def _command_queue_processor_cb(self):
        """GLib timeout callback to process commands from the input_handler queue."""
        if self.stop_requested_event.is_set():
            logger.info("Command queue processor stopping as service stop is requested.")
            return False # Do not reschedule

        processed_command = False
        try:
            while not self.command_queue.empty():
                if self.stop_requested_event.is_set(): break # Check again inside loop

                command = self.command_queue.get_nowait() # Non-blocking
                logger.debug(f"Processing command from queue: {command}")

                command_type = command.get('type')
                key_names = command.get('keys', []) # List of key names like "A", "LEFT_CTRL"

                if command_type == 'press':
                    self._update_report_for_keys(key_names, press=True)
                elif command_type == 'release':
                    self._update_report_for_keys(key_names, press=False)
                else:
                    logger.warning(f"Unknown command type in queue: {command_type}")

                self.command_queue.task_done()
                processed_command = True

            if processed_command:
                self._try_send_current_report_if_changed()

        except Exception as e:
            logger.exception("Error in command queue processor callback")

        return True # Reschedule this callback


    def _update_report_for_keys(self, key_names_list, press):
        """
        Updates the internal self.report_state based on a list of key names.
        key_names_list: A list of strings like ["LEFT_CTRL", "C"].
        press: Boolean, True to press, False to release.
        """
        if not isinstance(key_names_list, list):
            logger.warning(f"key_names_list is not a list: {key_names_list}. Skipping update.")
            return

        for key_name in key_names_list:
            if not key_name or key_name.upper() == "NONE": continue # Skip empty or "NONE" keys

            mod_mask_for_key, key_code_for_key = self.keycode_map.get_codes(key_name)

            # Update modifier byte (self.report_state[0])
            if mod_mask_for_key != self.keycode_map.MOD_NONE: # If this key IS a modifier
                if press:
                    self.report_state[0] |= mod_mask_for_key
                else:
                    self.report_state[0] &= ~mod_mask_for_key

            # Update regular key codes (self.report_state[2] to self.report_state[7])
            # Only if the key_code_for_key is not 0x00 (which it is for pure modifier keys)
            if key_code_for_key != 0x00:
                if press:
                    # Add key_code if not already present in report_state[2:8] and there's space
                    is_present = False
                    first_empty_slot = -1
                    for i in range(2, 8): # Slots for keycodes are index 2 through 7
                        if self.report_state[i] == key_code_for_key:
                            is_present = True
                            break
                        if self.report_state[i] == 0x00 and first_empty_slot == -1:
                            first_empty_slot = i
                    if not is_present and first_empty_slot != -1:
                        self.report_state[first_empty_slot] = key_code_for_key
                    elif not is_present: # and first_empty_slot == -1 (no space)
                        logger.warning(f"HID report key slots full (max 6). Cannot press '{key_name}'. Current: {self.report_state[2:].hex()}")
                else: # Release
                    # Remove key_code from report_state[2:8]
                    for i in range(2, 8):
                        if self.report_state[i] == key_code_for_key:
                            self.report_state[i] = 0x00
                            # Typically, HID keyboards don't re-pack keys on release, just zero them out.
                            # If repacking is desired (to always fill from left):
                            # temp_keys = [k for k in self.report_state[2:8] if k != 0x00]
                            # self.report_state[2:8] = bytearray(temp_keys + [0x00]*(6-len(temp_keys)))
                            break # Assuming a key is only pressed once

        logger.debug(f"Report state after update for '{key_names_list}' (press={press}): {self.report_state.hex()}")


    def _try_send_current_report_if_changed(self):
        """Sends the current keyboard report state if it changed from the last sent state."""
        if self.report_state != self.last_sent_report_state:
            if self.active_connection_profile:
                # Report ID for standard keyboard is 0x01, but often not prefixed if descriptor only has one report.
                # The provided descriptor seems to imply no explicit report ID prefix for keyboard data.
                # If issues, try report = b'\x01' + self.report_state
                report_to_send = bytes(self.report_state) # Ensure it's bytes
                if self.active_connection_profile.send_report(report_to_send):
                    self.last_sent_report_state = self.report_state[:] # Store a copy
            else:
                 logger.debug("No active HID connection to send report to.")
        # else:
            # logger.debug("Report state unchanged, not sending.")

    def _send_empty_report(self):
        """Sends an empty report (all keys up, no modifiers)."""
        empty_report = bytearray([0x00] * 8)
        if self.active_connection_profile:
            if self.active_connection_profile.send_report(bytes(empty_report)):
                 self.last_sent_report_state = empty_report[:]
                 self.report_state = empty_report[:] # Reset internal state too
        logger.info("Sent empty HID report (all keys up).")


    def register_active_connection(self, profile_conn_instance):
        """Called by HidProfile when a connection is successfully established."""
        if self.active_connection_profile and self.active_connection_profile != profile_conn_instance:
            logger.warning("New HID connection replacing an existing one. Cleaning up old.")
            self.active_connection_profile.cleanup_connection_resources() # Should call unregister
        self.active_connection_profile = profile_conn_instance
        dev_path = profile_conn_instance.get_device_path() if profile_conn_instance else "Unknown Device"
        logger.info(f"HID Service: Active connection registered with device {dev_path}.")
        # Send an initial empty report to clear any host-side state
        self._send_empty_report()


    def unregister_active_connection(self, profile_conn_instance):
        """Called by HidProfile when its connection is terminated."""
        dev_path = profile_conn_instance.get_device_path() if profile_conn_instance else "Unknown Device"
        if self.active_connection_profile == profile_conn_instance:
            self.active_connection_profile = None
            # Reset report state on disconnect to avoid stale key presses on reconnect
            self.report_state = bytearray([0x00] * 8)
            self.last_sent_report_state = bytearray([0x00] * 8)
            logger.info(f"HID Service: Active connection with {dev_path} unregistered.")
        else:
             logger.warning(f"Attempt to unregister an unknown/inactive connection profile for {dev_path}.")


    def run(self, device_name="NixMacroPad"):
        """Main loop for the HID service. This function will block until stop() is called."""
        logger.info(f"HID Service starting with device name '{device_name}'...")
        if not self._init_dbus_and_mainloop():
            logger.critical("Failed to initialize D-Bus and Mainloop. HID Service cannot start.")
            return

        if not self._find_adapter():
            logger.critical("Bluetooth adapter not found. HID Service cannot start.")
            self.stop() # Ensure mainloop doesn't run if it was started
            return

        if not self._set_adapter_properties(device_name=device_name):
            logger.warning("Failed to set some adapter properties. Continuing, but pairing/discovery might be affected.")
            # Don't necessarily stop, BlueZ might still work with defaults.

        if not self._register_hid_profile():
            logger.critical("Failed to register HID profile. HID Service cannot start.")
            self.stop()
            return

        # Add command queue processor to the main loop, checks every ~20ms
        # Lower value for more responsiveness, higher for less CPU.
        # Needs to be frequent enough to feel responsive.
        GObject.timeout_add(20, self._command_queue_processor_cb)
        logger.info("HID Service command queue processor scheduled.")
        logger.info("HID Service running. Waiting for connections/commands...")

        try:
            self.mainloop.run() # This blocks until self.mainloop.quit() is called
        except KeyboardInterrupt:
            logger.info("HID Service interrupted by user (KeyboardInterrupt).")
        except Exception as e:
            logger.exception(f"Error running HID service main loop: {e}")
        finally:
            logger.info("HID Service main loop exited.")
            # Cleanup is handled in stop(), which should be called by the main app's on_stop or equivalent.
            # If run() exits due to an error before stop() is called from outside,
            # we should ensure cleanup here too.
            if not self.stop_requested_event.is_set(): # If stop wasn't called explicitly
                self.perform_cleanup()


    def perform_cleanup(self):
        logger.info("Performing HidService cleanup...")
        # Order matters: first, tell connected profile to clean up, then unregister from BlueZ.
        if self.active_connection_profile:
            logger.info("Cleaning up active connection profile as part of HidService shutdown.")
            self.active_connection_profile.cleanup_connection_resources() # This will call unregister_active_connection
            self.active_connection_profile = None # Ensure it's cleared

        self._unregister_hid_profile()

        # Other cleanups like removing D-Bus signal watches if any were added directly by HidService.
        logger.info("HidService cleanup finished.")


    def stop(self):
        """Stops the HID service and cleans up resources."""
        logger.info("HID Service stop requested.")
        self.stop_requested_event.set() # Signal all loops/callbacks to stop

        if self.mainloop and self.mainloop.is_running():
            logger.info("Requesting GLib MainLoop to quit.")
            # It's safer to call quit from within the mainloop's thread context if possible,
            # or ensure callbacks check self.stop_requested_event.
            # For an external call like this, GLib.idle_add(self.mainloop.quit) can be safer.
            # However, direct quit is often used and usually works if called from another thread.
            self.mainloop.quit()
        else:
            logger.info("GLib MainLoop not running or not initialized.")

        # Cleanup is now primarily in perform_cleanup(), called when mainloop exits.
        # If perform_cleanup wasn't reached (e.g., mainloop never ran), call it here.
        # This check is a bit complex. Simpler: main_gui_app ensures stop() is called,
        # and run() calls perform_cleanup() in its finally block.
