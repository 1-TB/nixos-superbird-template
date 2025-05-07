#!/usr/bin/env python3

import kivy
kivy.require('2.1.0') # Or a version compatible with your Nixpkgs

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.properties import BooleanProperty, ListProperty, StringProperty, ObjectProperty
from kivy.clock import Clock, mainthread
from kivy.core.window import Window

import threading
from queue import Queue
import os
import logging
import json # For a more complex key picker later

# Project backend modules
from backend.config_manager import ConfigManager
from backend.keycodes import KeycodeMap
from backend.input_handler import InputHandler
from backend.hid_service import HidService

# --- Logging Configuration ---
# Kivy's logger can be used, or Python's standard logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MacroPadApp")

# --- Global Command Queue for HID Service ---
command_queue = Queue()

# --- Kivy UI Elements ---

class MappingEntryWidget(RecycleDataViewBehavior, BoxLayout):
    ''' A widget for displaying a single mapping entry in a RecycleView. '''
    index = None  # Stores the index of the data item

    action_name_prop = StringProperty('')
    action_type_prop = StringProperty('')
    action_keys_prop = StringProperty('')
    app_instance_prop = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.spacing = '10dp'
        self.size_hint_y = None
        self.height = '60dp' # Adjust as needed

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes. '''
        self.index = index
        self.action_name_prop = data.get('action_name', '')
        self.action_type_prop = data.get('action_type', '')
        self.action_keys_prop = ", ".join(data.get('keys', []))
        self.app_instance_prop = data.get('app_instance')
        return super().refresh_view_attrs(rv, index, data)

    def on_edit_press(self, action_name):
        if self.app_instance_prop:
            logger.info(f"Edit pressed for: {action_name}")
            self.app_instance_prop.edit_specific_mapping(action_name)


class EditMappingScreen(Screen):
    action_name_label = ObjectProperty(None)
    type_spinner = ObjectProperty(None)
    keys_label = ObjectProperty(None) # For displaying current keys
    # TODO: Add key picker UI elements

    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.current_action_name = ""
        self.current_keys = []
        self.available_key_names = sorted(list(self.app_instance.keycode_map.NAME_TO_CODE.keys()))

    def load_action(self, action_name):
        self.current_action_name = action_name
        mapping = self.app_instance.config_manager.get_mappings().get(action_name)
        if not mapping:
            logger.error(f"Could not load action {action_name} for editing.")
            self.go_back()
            return

        self.action_name_label.text = f"Editing: {self.app_instance.format_action_name_display(action_name)}"
        self.type_spinner.text = self.app_instance.format_type_name_display(mapping.get('type', 'none'))
        self.current_keys = list(mapping.get('keys', [])) # Make a mutable copy
        self.update_keys_display()

    def update_keys_display(self):
        self.keys_label.text = f"Keys: {', '.join(self.current_keys) if self.current_keys else 'None'}"

    def add_key_popup(self):
        # This would open a popup with a key selector (e.g., another RecycleView or Spinner)
        # For simplicity, we'll simulate adding a key.
        # In a real app, this would be a more complex UI interaction.
        if self.available_key_names:
            # Example: Add the first available key if not already present and less than 6 keys
            if len(self.current_keys) < 6:
                key_to_add = "A" # Placeholder, should come from picker
                # Find a key that is not 'NONE' and not already in current_keys
                for key_name_option in self.available_key_names:
                    if key_name_option != "NONE" and key_name_option not in self.current_keys:
                        key_to_add = key_name_option
                        break

                if key_to_add not in self.current_keys:
                    self.current_keys.append(key_to_add)
                    self.update_keys_display()
                else:
                    self.app_instance.show_status_popup("Info", f"{key_to_add} is already added.")
            else:
                self.app_instance.show_status_popup("Warning", "Maximum of 6 keys reached for this action.")


    def remove_last_key(self):
        if self.current_keys:
            self.current_keys.pop()
            self.update_keys_display()

    def save_current_mapping(self):
        if not self.current_action_name:
            return

        action_type_internal = self.app_instance.format_type_name_internal(self.type_spinner.text)
        updated_mappings = self.app_instance.config_manager.get_mappings()
        updated_mappings[self.current_action_name] = {
            "type": action_type_internal,
            "keys": list(self.current_keys) # Save a copy
        }
        if self.app_instance.config_manager.update_mappings(updated_mappings):
            self.app_instance.show_status_popup("Success", "Mapping saved!")
            self.app_instance.input_handler.load_mappings() # Crucial: reload in input_handler
            self.app_instance.refresh_mappings_display_on_config_screen()
            self.go_back()
        else:
            self.app_instance.show_status_popup("Error", "Failed to save mapping.")

    def go_back(self):
        self.manager.current = 'config'
        self.manager.transition.direction = 'right'


class ConfigScreen(Screen):
    mappings_rv = ObjectProperty(None)

    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        Clock.schedule_once(self.populate_mappings, 0.1) # Populate after UI is built

    def populate_mappings(self, *args):
        mappings_data = []
        raw_mappings = self.app_instance.config_manager.get_mappings()
        # Ensure a consistent order for display
        sorted_action_names = sorted(raw_mappings.keys())

        for action_name in sorted_action_names:
            mapping = raw_mappings[action_name]
            mappings_data.append({
                'action_name': action_name,
                'action_type': self.app_instance.format_type_name_display(mapping.get('type', 'none')),
                'keys': mapping.get('keys', []),
                'app_instance': self.app_instance # Pass app instance for callbacks
            })
        if self.mappings_rv:
            self.mappings_rv.data = mappings_data
        else:
            logger.warning("Mappings RV not available yet in ConfigScreen.")

    def refresh_mappings(self):
        self.populate_mappings()

class StatusPopup(BoxLayout):
    status_title = StringProperty('')
    status_text = StringProperty('')
    popup_instance = ObjectProperty(None)

    def dismiss_popup(self):
        if self.popup_instance:
            self.popup_instance.dismiss()

class MacroPadGUIApp(App):
    def build(self):
        self.title = "NixOS MacroPad"
        Window.clearcolor = (0.15, 0.15, 0.15, 1) # Dark background

        # --- Configurable Paths ---
        # For a production app on NixOS, this config file should be in a standard user/system config directory.
        # For now, assume it's in the same directory as the script or a predefined writable path.
        # Example: data_dir = os.path.expanduser("~/.config/nixos_macropad")
        # os.makedirs(data_dir, exist_ok=True)
        # config_file_path = os.path.join(data_dir, "config.json")
        config_file_path = "config.json" # Simpler for now
        logger.info(f"Using configuration file: {config_file_path}")

        self.config_manager = ConfigManager(config_file_path)
        self.keycode_map = KeycodeMap()

        # --- Critical: Define correct device paths ---
        # These paths MUST be discovered using `evtest` on the Car Thing
        # and ideally passed via environment variables or a config file managed by NixOS.
        default_knob_path = "/dev/input/eventX" # REPLACE THIS
        default_button_path = "/dev/input/eventY" # REPLACE THIS

        knob_dev_path = os.environ.get("KNOB_DEVICE_PATH", default_knob_path)
        button_dev_path = os.environ.get("BUTTON_DEVICE_PATH", default_button_path)

        input_devices = []
        if os.path.exists(knob_dev_path) and os.access(knob_dev_path, os.R_OK):
            input_devices.append(knob_dev_path)
            logger.info(f"Found and using knob device: {knob_dev_path}")
        else:
            logger.warning(f"Knob device not found or not readable: {knob_dev_path}. Check path and permissions.")

        if os.path.exists(button_dev_path) and os.access(button_dev_path, os.R_OK):
            if button_dev_path not in input_devices: # Avoid duplicates if same device
                 input_devices.append(button_dev_path)
            logger.info(f"Found and using button device: {button_dev_path}")
        else:
            logger.warning(f"Button device not found or not readable: {button_dev_path}. Check path and permissions.")

        if not input_devices:
            logger.error("CRITICAL: No input devices specified or found. Input handling will not work.")
            # Optionally, show a popup or exit
            # self.show_status_popup("Critical Error", "No input devices. Check logs.")


        # Initialize backend services
        self.hid_service = HidService(command_queue)
        self.input_handler = InputHandler(input_devices, command_queue, self.config_manager)

        # Start backend threads
        self.hid_thread = threading.Thread(target=self.hid_service.run, name="HidServiceThread", daemon=True)
        self.input_thread = threading.Thread(target=self.input_handler.run, name="InputHandlerThread", daemon=True)

        self.hid_thread.start()
        logger.info("HID Service thread started.")
        self.input_thread.start()
        logger.info("Input Handler thread started.")

        # Setup Kivy Screen Manager
        self.screen_manager = ScreenManager()
        self.config_screen = ConfigScreen(name='config', app_instance=self)
        self.edit_mapping_screen = EditMappingScreen(name='edit_mapping', app_instance=self)

        self.screen_manager.add_widget(self.config_screen)
        self.screen_manager.add_widget(self.edit_mapping_screen)

        # For debugging input events (optional)
        # Clock.schedule_interval(self.check_command_queue_debug, 1)
        return self.screen_manager

    def check_command_queue_debug(self, dt):
        # For debugging if HID commands are being generated
        if not command_queue.empty():
            item = command_queue.queue[0] # Peek
            logger.debug(f"DEBUG: Command Queue peek: {item}")


    def format_action_name_display(self, action_name_internal):
        return action_name_internal.replace("_", " ").title()

    def format_type_name_display(self, type_name_internal):
        return {
            "key_tap": "Tap (Press & Release)",
            "key_press": "Press Only",
            "key_release": "Release Only",
            "none": "None"
        }.get(type_name_internal, type_name_internal.title())

    def format_type_name_internal(self, type_name_display):
         return {
            "Tap (Press & Release)": "key_tap",
            "Press Only": "key_press",
            "Release Only": "key_release",
            "None": "none"
        }.get(type_name_display, type_name_display.lower())


    def edit_specific_mapping(self, action_name):
        self.edit_mapping_screen.load_action(action_name)
        self.screen_manager.current = 'edit_mapping'
        self.screen_manager.transition.direction = 'left'

    def refresh_mappings_display_on_config_screen(self):
        if self.config_screen:
            self.config_screen.refresh_mappings()

    def show_status_popup(self, title, message):
        from kivy.uix.popup import Popup
        content = StatusPopup(status_title=title, status_text=message)
        popup = Popup(title=title,
                      content=content,
                      size_hint=(0.7, 0.4),
                      auto_dismiss=False)
        content.popup_instance = popup # Give content a reference to its popup
        popup.open()


    def on_stop(self):
        logger.info("Stopping MacroPad Application...")
        if hasattr(self, 'input_handler') and self.input_handler:
            self.input_handler.stop()
        if hasattr(self, 'hid_service') and self.hid_service:
            # HidService's stop needs to ensure its GLib main loop quits.
            # It might involve calling self.io_loop.quit() from within the HidService's thread context
            # or having a flag that its Glib.timeout_add checks.
            self.hid_service.stop()

        # Wait for threads to finish
        threads_to_join = []
        if hasattr(self, 'input_thread') and self.input_thread.is_alive():
            threads_to_join.append(self.input_thread)
        if hasattr(self, 'hid_thread') and self.hid_thread.is_alive():
            threads_to_join.append(self.hid_thread)

        for t in threads_to_join:
            logger.info(f"Joining thread: {t.name}")
            t.join(timeout=2) # Wait for 2 seconds
            if t.is_alive():
                logger.warning(f"Thread {t.name} did not terminate in time.")

        logger.info("Application stopped.")

if __name__ == '__main__':
    # It's good practice to ensure this script is executable: chmod +x main_gui_app.py
    # Kivy settings via environment variables (if needed for Car Thing)
    # e.g., os.environ['KIVY_WINDOW'] = 'egl_rpi' # Example for Raspberry Pi
    # os.environ['KIVY_GRAPHICS_BACKEND'] = 'gl'
    # os.environ['KIVY_INPUT_PROVIDER'] = 'hidinput' # Or 'mtdev' for multi-touch

    # Set KIVY_HOME to a writable directory for Kivy's internal config/cache
    # This is important on a read-only NixOS root filesystem.
    # The path should be created and made writable by your NixOS config.
    kivy_home_path = os.environ.get("KIVY_HOME_PATH", "/tmp/kivy_home_macropad") # Example
    if not os.path.exists(kivy_home_path):
        try:
            os.makedirs(kivy_home_path, exist_ok=True)
            logger.info(f"Created KIVY_HOME directory: {kivy_home_path}")
        except Exception as e:
            logger.error(f"Could not create KIVY_HOME directory {kivy_home_path}: {e}")
    os.environ['KIVY_HOME'] = kivy_home_path
    logger.info(f"KIVY_HOME set to: {os.environ.get('KIVY_HOME')}")

    MacroPadGUIApp().run()
