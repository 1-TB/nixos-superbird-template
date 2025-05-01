import logging
from flask import Flask, jsonify, render_template, request, send_from_directory
import os

logger = logging.getLogger("WebServer")

class WebServer:
    def __init__(self, config_manager, input_handler):
        self.config_manager = config_manager
        self.input_handler = input_handler # To potentially reload mappings after update

        # Determine path to frontend files (assuming relative path from backend dir)
        frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
        logger.info(f"Serving frontend files from: {frontend_folder}")

        # Use template_folder and static_folder arguments for Flask
        self.app = Flask(__name__,
                         template_folder=frontend_folder,
                         static_folder=frontend_folder)

        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/')
        def index():
            # Render the main HTML page
            return render_template('index.html')

        # Serve static files (CSS, JS) - Flask does this automatically if named 'static'
        # but explicit route can be clearer or needed if folder name differs.
        @self.app.route('/<path:filename>')
        def serve_static(filename):
             return send_from_directory(self.app.static_folder, filename)

        @self.app.route('/api/mappings', methods=['GET'])
        def get_mappings():
            mappings = self.config_manager.get_mappings()
            return jsonify(mappings)

        @self.app.route('/api/mappings', methods=['POST'])
        def set_mappings():
            try:
                new_mappings = request.get_json()
                if not new_mappings:
                    return jsonify({"status": "error", "message": "No data received"}), 400

                logger.info(f"Received new mappings via API: {new_mappings}")
                success = self.config_manager.update_mappings(new_mappings)

                if success:
                    # Tell input handler to reload the configuration
                    self.input_handler.load_mappings()
                    logger.info("Input handler reloaded mappings.")
                    return jsonify({"status": "success", "message": "Mappings updated successfully"})
                else:
                    return jsonify({"status": "error", "message": "Failed to save mappings"}), 500
            except Exception as e:
                 logger.exception("Error processing set_mappings request")
                 return jsonify({"status": "error", "message": f"Internal server error: {e}"}), 500

        # Add routes for listing available keys/actions if needed
        @self.app.route('/api/available-keys', methods=['GET'])
        def get_available_keys():
             # Import here to avoid circular dependency at module level if needed
             from keycodes import KeycodeMap
             kc_map = KeycodeMap()
             return jsonify(list(kc_map.NAME_TO_CODE.keys()))

        @self.app.route('/api/available-actions', methods=['GET'])
        def get_available_actions():
            # These are the keys used in the default config and input_handler
             actions = [
                 "knob_cw", "knob_ccw",
                 "front_button_press", "front_button_release",
                 "top_button_1_press", "top_button_1_release",
                 "top_button_2_press", "top_button_2_release",
                 "top_button_3_press", "top_button_3_release",
                 "top_button_4_press", "top_button_4_release",
             ]
             return jsonify(actions)


    def run(self, host='0.0.0.0', port=5000, debug=False):
         logger.info(f"Starting Flask server on {host}:{port}")
         # Use 'waitress' or 'gunicorn' for a more production-ready server via Nix config
         self.app.run(host=host, port=port, debug=debug)