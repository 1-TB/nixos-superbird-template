#!/usr/bin/env python3

import sys
import os
import threading
import argparse
import logging
from queue import Queue

# Make sure backend modules can be imported
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from input_handler import InputHandler
from hid_service import HidService
from config_manager import ConfigManager
from web_server import WebServer

# --- Configuration ---
LOG_LEVEL = logging.INFO
CONFIG_FILE_PATH = "config.json" # Default, overridden by args
# --- Hardware Placeholders ---
# You MUST replace these with paths discovered via `evtest` on your device
KNOB_DEVICE_PATH = "/dev/input/eventX"  # Placeholder
BUTTON_DEVICE_PATH = "/dev/input/eventY" # Placeholder

# Queue for commands from input handler to HID service
command_queue = Queue()

# Setup logging
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Main")

def main():
    parser = argparse.ArgumentParser(description="NixOS Macro Pad Backend Service")
    parser.add_argument('--config', type=str, default=CONFIG_FILE_PATH, help='Path to the configuration file')
    # Add arguments for device paths if needed, although discovery might be better
    # parser.add_argument('--knob-dev', type=str, default=KNOB_DEVICE_PATH)
    # parser.add_argument('--button-dev', type=str, default=BUTTON_DEVICE_PATH)
    args = parser.parse_args()

    logger.info(f"Starting Macro Pad Backend using config: {args.config}")

    config_manager = ConfigManager(args.config)

    # --- Initialize Services ---
    try:
        # Start HID Service (Needs to run first to setup D-Bus)
        hid_service = HidService(command_queue)
        hid_thread = threading.Thread(target=hid_service.run, daemon=True)
        hid_thread.start()
        logger.info("HID Service thread started.")

        # Start Input Handler
        # Pass the actual device paths here
        input_devices = [KNOB_DEVICE_PATH, BUTTON_DEVICE_PATH]
        input_handler = InputHandler(input_devices, command_queue, config_manager)
        input_thread = threading.Thread(target=input_handler.run, daemon=True)
        input_thread.start()
        logger.info("Input Handler thread started.")

        # Start Web Server (Flask)
        web_server = WebServer(config_manager, input_handler) # Pass dependencies
        # Run Flask in the main thread or its own thread if preferred
        # Note: Flask's development server is not recommended for production.
        # Consider using `waitress` or `gunicorn` via Nix if needed.
        logger.info("Starting Web Server...")
        web_server.run() # This will block the main thread

    except Exception as e:
        logger.exception(f"Critical error during initialization or runtime: {e}")
        sys.exit(1)

    finally:
        logger.info("Macro Pad Backend attempting clean shutdown.")
        # Add cleanup logic if needed (e.g., hid_service.stop())
        # Note: daemon threads might not allow clean shutdown on exit signal

if __name__ == "__main__":
    main()