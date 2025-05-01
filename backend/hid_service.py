import dbus
import dbus.service
import dbus.mainloop.glib
import logging
import time
import threading
from gi.repository import GLib # Use GObject main loop for D-Bus

# Import keycodes - make sure this file exists and is correct
from keycodes import KeycodeMap

logger = logging.getLogger("HidService")

# --- D-Bus Constants (BlueZ HID Profile) ---
BLUEZ_SERVICE_NAME = 'org.bluez'
ADAPTER_INTERFACE = 'org.bluez.Adapter1'
DEVICE_INTERFACE = 'org.bluez.Device1'
PROFILE_MANAGER_INTERFACE = 'org.bluez.ProfileManager1'
HID_PROFILE_INTERFACE = 'org.bluez.HidProfile1' # Custom profile interface name
HID_DBUS_PATH = '/org/bluez/custom_hid_profile' # Custom path for our profile registration
SDP_RECORD_XML = """
<?xml version="1.0" encoding="UTF-8" ?>
<record>
  <attribute id="0x0001"> <sequence>
      <uuid value="0x1124" /> </sequence>
  </attribute>
  <attribute id="0x0004"> <sequence>
      <sequence>
        <uuid value="0x0100" /> <uint16 value="0x0011" /> </sequence>
      <sequence>
        <uuid value="0x0011" /> </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0005"> <sequence>
        <uuid value="0x1002" />
      </sequence>
  </attribute>
  <attribute id="0x0006"> <sequence>
      <uint16 value="0x656e" />
      <uint16 value="0x006a" />
      <uint16 value="0x0100" />
    </sequence>
  </attribute>
  <attribute id="0x0009"> <sequence>
      <sequence>
        <uuid value="0x1124" /> <uint16 value="0x0101" /> </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100"> <text value="NixOS MacroPad HID" />
  </attribute>
  <attribute id="0x0101"> <text value="Bluetooth HID Keyboard" />
  </attribute>
  <attribute id="0x0102"> <text value="NixOS-Superbird" />
  </attribute>

  <attribute id="0x0201"> <uint16 value="0x0111" /> </attribute>
  <attribute id="0x0202"> <uint8 value="0x40" /> </attribute>
  <attribute id="0x0203"> <uint8 value="0x00" /> </attribute>
  <attribute id="0x0204"> <boolean value="true" />
  </attribute>
  <attribute id="0x0205"> <boolean value="true" />
  </attribute>
  <attribute id="0x0206"> <sequence>
      <sequence>
        <uint8 value="0x22" /> <text value="05010906a101050719e029e71500250175019508810295017508810395057501050819012905910295017503910395067508150025650507190029658100c0" />
       </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0207"> <sequence>
        <sequence>
          <uint16 value="0x0409" /> <uint16 value="0x0100" />
        </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0209"> <boolean value="true" />
  </attribute>
  <attribute id="0x020B"> <boolean value="false" />
  </attribute>
  <attribute id="0x020E"> <boolean value="true" />
  </attribute>
</record>
"""

class HidProfile(dbus.service.Object):
    """
    Custom BlueZ HID Profile implementation.
    Handles connection requests and provides communication channels.
    """
    def __init__(self, bus, path, hid_service):
        super().__init__(bus, path)
        self.hid_service = hid_service
        self.device = None # Stores the connected device proxy
        self.control_channel = None # L2CAP Control Channel socket (if needed)
        self.interrupt_channel = None # L2CAP Interrupt Channel socket

    @dbus.service.method(PROFILE_MANAGER_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        logger.info("HID Profile Release called")
        # Potentially disconnect device here if needed

    @dbus.service.method(PROFILE_MANAGER_INTERFACE, in_signature="o{sv}", out_signature="")
    def NewConnection(self, device_path, fd_dict):
        logger.info(f"New HID Connection from device: {device_path}")
        try:
            device_obj = self.hid_service.bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            self.device = dbus.Interface(device_obj, DEVICE_INTERFACE)

            # Get file descriptor for the interrupt channel (main communication)
            fd = fd_dict['fd'].take()
            self.interrupt_channel = self.hid_service.io_loop.add_watch(
                fd,
                GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, # Watch for input/hangup/error
                self.interrupt_channel_event
            )
            logger.info(f"Interrupt channel FD {fd} setup.")

            # Store the connection details in the parent HidService
            self.hid_service.register_connection(self)

        except Exception as e:
            logger.exception(f"Error setting up new HID connection: {e}")
            # Maybe close FD if obtained?

    @dbus.service.method(PROFILE_MANAGER_INTERFACE, in_signature="o", out_signature="")
    def RequestDisconnection(self, device_path):
        logger.warning(f"HID Disconnection requested for device: {device_path}")
        if self.device and self.device.object_path == device_path:
            self.cleanup_connection()
        else:
             logger.warning("Disconnection request for unknown or non-matching device.")

    def interrupt_channel_event(self, fd, conditions):
        """Callback when data is available or connection closed on interrupt channel."""
        if conditions & GLib.IO_IN:
            try:
                # Read data received from host (e.g., LED status updates)
                # We don't process incoming reports in this basic example
                data = os.read(fd, 1024)
                logger.debug(f"Received data on interrupt channel (fd {fd}): {data.hex()}")
                # Handle SET_REPORT, GET_REPORT if needed based on data content
            except OSError as e:
                logger.error(f"Error reading interrupt channel (fd {fd}): {e}")
                self.cleanup_connection()
                return False # Remove watch

        if conditions & (GLib.IO_HUP | GLib.IO_ERR):
            logger.warning(f"Interrupt channel (fd {fd}) closed or error (HUP/ERR). Conditions: {conditions}")
            self.cleanup_connection()
            return False # Remove watch

        return True # Keep watch active

    def send_report(self, report):
        """Sends a HID report over the interrupt channel."""
        if self.interrupt_channel and self.interrupt_channel.unix_fd is not None:
            try:
                os.write(self.interrupt_channel.unix_fd, report)
                logger.debug(f"Sent report: {report.hex()}")
            except OSError as e:
                logger.error(f"Failed to send report: {e}")
                self.cleanup_connection()
        else:
            logger.warning("Cannot send report: No active interrupt channel.")

    def cleanup_connection(self):
        logger.info("Cleaning up HID connection.")
        if self.interrupt_channel:
            fd = self.interrupt_channel.unix_fd
            if fd is not None:
                 GLib.source_remove(self.interrupt_channel.source_id)
                 try:
                    os.close(fd)
                    logger.info(f"Closed interrupt channel FD {fd}")
                 except OSError as e:
                    logger.error(f"Error closing interrupt channel FD {fd}: {e}")
            self.interrupt_channel = None

        # Inform HidService that this connection is gone
        if self.hid_service:
            self.hid_service.unregister_connection(self)
        self.device = None

class HidService:
    """Manages BlueZ D-Bus interaction and HID report sending."""
    def __init__(self, command_queue):
        self.command_queue = command_queue
        self.bus = None
        self.profile = None
        self.adapter = None
        self.io_loop = None # GObject main loop
        self.stop_event = threading.Event()
        self.current_connection = None # Stores the active HidProfile instance
        self.keycode_map = KeycodeMap()

        # Keyboard report state [Modifier, Reserved, Key1, Key2, Key3, Key4, Key5, Key6]
        self.report_state = bytearray([0x00] * 8)

    def register_connection(self, profile_instance):
        """Called by HidProfile when a connection is established."""
        if self.current_connection and self.current_connection != profile_instance:
            logger.warning("New connection replacing existing one. Cleaning up old.")
            self.current_connection.cleanup_connection() # Should auto-call unregister
        self.current_connection = profile_instance
        logger.info("HID Service connection registered.")

    def unregister_connection(self, profile_instance):
        """Called by HidProfile when a connection is terminated."""
        if self.current_connection == profile_instance:
            self.current_connection = None
            self.report_state = bytearray([0x00] * 8) # Reset report state on disconnect
            logger.info("HID Service connection unregistered.")
        else:
             logger.warning("Attempt to unregister an unknown/inactive connection.")

    def _setup_dbus(self):
        """Initializes D-Bus connection and main loop."""
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        self.io_loop = GLib.MainLoop()

    def _register_profile(self):
        """Registers the custom HID profile with BlueZ."""
        profile_manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, '/org/bluez'),
            PROFILE_MANAGER_INTERFACE
        )

        # Create and register our profile implementation
        self.profile = HidProfile(self.bus, HID_DBUS_PATH, self)

        opts = {
            "ServiceRecord": SDP_RECORD_XML,
            "Role": "server", # Acting as the HID device (server)
            "RequireAuthentication": False, # Allow connections without host pairing PIN entry
            "RequireAuthorization": False,
            "AutoConnect": True,
            # "Name": "NixOS MacroPad HID", # Might override SDP Name
            "PSM": dbus.UInt16(0x0011), # HID Control - Optional if SDP handles it
            "Service": dbus.String("00001124-0000-1000-8000-00805f9b34fb") # HID Service UUID
        }

        try:
            profile_manager.RegisterProfile(HID_DBUS_PATH, "00001124-0000-1000-8000-00805f9b34fb", opts)
            logger.info("HID Profile registered successfully.")
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to register HID profile: {e}")
            # Handle potential errors like "Already Exists" if necessary
            raise

    def _find_adapter(self):
         """Finds the default Bluetooth adapter."""
         om = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, '/'), 'org.freedesktop.DBus.ObjectManager')
         objects = om.GetManagedObjects()
         for path, interfaces in objects.items():
             if ADAPTER_INTERFACE in interfaces:
                 logger.info(f"Found Bluetooth adapter: {path}")
                 self.adapter = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, path), ADAPTER_INTERFACE)
                 return True
         logger.error("Could not find a Bluetooth adapter.")
         return False

    def _set_adapter_properties(self):
        """Sets the adapter to be discoverable and pairable."""
        if not self.adapter: return
        try:
            props = dbus.Interface(self.adapter, 'org.freedesktop.DBus.Properties')
            props.Set(ADAPTER_INTERFACE, "Discoverable", dbus.Boolean(True))
            props.Set(ADAPTER_INTERFACE, "Pairable", dbus.Boolean(True))
            props.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(True)) # Ensure adapter is on
            logger.info("Adapter set to Discoverable and Pairable.")
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to set adapter properties: {e}")

    def _process_command_queue(self):
        """Periodically checks the queue for commands and sends reports."""
        while not self.command_queue.empty():
            command = self.command_queue.get()
            logger.debug(f"Processing command: {command}")

            command_type = command.get('type')
            keys = command.get('keys', [])

            if command_type == 'press':
                self.update_report_state(keys, press=True)
            elif command_type == 'release':
                self.update_report_state(keys, press=False)
            else:
                logger.warning(f"Unknown command type in queue: {command_type}")

            self.send_current_report()
            self.command_queue.task_done() # Mark task as completed

        # Reschedule the check
        if not self.stop_event.is_set():
             GLib.timeout_add(5, self._process_command_queue) # Check every 5ms

        return False # Stop timeout if stop_event is set

    def update_report_state(self, key_names, press):
        """Updates the internal keyboard report state based on key names."""
        for key_name in key_names:
            mod_code, key_code = self.keycode_map.get_codes(key_name)

            # Update modifier byte
            if mod_code is not None:
                if press:
                    self.report_state[0] |= mod_code
                else:
                    self.report_state[0] &= ~mod_code

            # Update regular key codes (first 6 available slots)
            if key_code is not None and key_code != 0x00:
                 # Add key on press if not already present
                 if press:
                     # Find first empty slot (0x00) starting from index 2
                     try:
                         empty_index = self.report_state.index(0x00, 2)
                         # Check if key already in report to avoid duplicates
                         if key_code not in self.report_state[2:]:
                             self.report_state[empty_index] = key_code
                     except ValueError:
                         logger.warning("Keyboard report key slots full (max 6 simultaneous keys).")
                 # Remove key on release
                 else:
                     for i in range(2, 8):
                         if self.report_state[i] == key_code:
                             self.report_state[i] = 0x00
                             break # Remove only one instance

        logger.debug(f"Updated report state: {self.report_state.hex()}")


    def send_current_report(self):
        """Sends the current keyboard report state over the active connection."""
        if self.current_connection:
            # Prepend HID report ID (usually 0x01 for keyboard) - Check descriptor if unsure
            # For the standard descriptor above, no explicit ID prefix is needed for keyboard reports
            # report = b'\x01' + self.report_state
            report = bytes(self.report_state)
            self.current_connection.send_report(report)
        else:
             logger.debug("No active connection to send report.")


    def run(self):
        """Main loop for the HID service."""
        logger.info("HID Service starting...")
        try:
            self._setup_dbus()
            if not self._find_adapter():
                raise RuntimeError("Bluetooth adapter not found.")
            self._set_adapter_properties()
            self._register_profile()

            # Start command queue processing
            GLib.timeout_add(10, self._process_command_queue) # Start checking queue after 10ms

            logger.info("HID Service running. Waiting for connections/commands...")
            self.io_loop.run() # Start the GObject main loop

        except Exception as e:
            logger.exception(f"Error running HID service: {e}")
        finally:
            logger.info("HID Service stopping...")
            self.stop() # Ensure cleanup happens

    def stop(self):
        """Stops the service and cleans up resources."""
        self.stop_event.set()
        if self.io_loop and self.io_loop.is_running():
            self.io_loop.quit()

        # Unregister profile (optional, BlueZ might clean up on disconnect)
        # try:
        #     if self.profile and self.bus:
        #          profile_manager = dbus.Interface(...)
        #          profile_manager.UnregisterProfile(HID_DBUS_PATH)
        #          logger.info("HID Profile unregistered.")
        # except Exception as e:
        #     logger.error(f"Failed to unregister profile: {e}")

        if self.current_connection:
            self.current_connection.cleanup_connection()

        logger.info("HID Service finished cleanup.")