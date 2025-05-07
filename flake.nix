{
  description = "NixOS Superbird configuration for MacroPad";

  inputs = {
    nixos-superbird.url = "github:1tb/nixos-superbird/main";
    nixpkgs.follows = "nixos-superbird/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, nixos-superbird, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          # overlays = [ nixos-superbird.overlays.default ];
          config.allowUnfree = true;
        };

        # Kivy application package
        nixos-macropad-app-pkg = pkgs.python3Packages.buildPythonApplication {
          pname = "nixos-macropad";
          version = "0.2.0";
          src = ./.; # Source is the current flake directory

          # Runtime dependencies for your Python app
          propagatedBuildInputs = with pkgs.python3Packages; [
            kivy # This pulls in SDL2 and other Kivy deps
            evdev
            dbus-python
            pygobject3 # For GLib main loop in HidService

          ];


          installPhase = ''
            runHook preInstall
            # Create structure expected by the wrapper script
            mkdir -p $out/lib/python${pkgs.python3.pythonVersion}/site-packages/backend
            cp main_gui_app.py $out/lib/python${pkgs.python3.pythonVersion}/site-packages/
            cp backend/*.py $out/lib/python${pkgs.python3.pythonVersion}/site-packages/backend/
            # Copy .kv file if it's not automatically found or if you load it explicitly
            cp macropad.kv $out/lib/python${pkgs.python3.pythonVersion}/site-packages/

            # Create the executable wrapper
            mkdir -p $out/bin
            cat > $out/bin/nixos-macropad-app-launcher <<EOF
            #!${pkgs.runtimeShell}
            # Environment variables for Kivy, if needed on the Car Thing
            # These are examples, you'll need to find what works for the Superbird's display
            # export KIVY_WINDOW=egl_rpi # Might be specific to Raspberry Pi
            # export KIVY_GRAPHICS_BACKEND=gles # Or 'gl'
            # export KIVY_GL_DEBUG=1 # For debugging OpenGL issues
            # export KIVY_LOG_LEVEL=info # Kivy's own logging level (debug, warning, error, info)

            # Path for Kivy's config, fonts, etc. Needs to be writable.
            export KIVY_HOME_PATH="/var/lib/nixos-macropad/kivy_home"
            mkdir -p "\$KIVY_HOME_PATH" # Ensure it exists

            # Paths for evdev input devices (MUST BE CORRECT FOR YOUR CAR THING)
            export KNOB_DEVICE_PATH="${config.hardware.macropad.knobDevicePath}"
            export BUTTON_DEVICE_PATH="${config.hardware.macropad.buttonDevicePath}"
            # Touchscreen might be auto-detected by Kivy if udev rules are correct.
            # If not, Kivy might need KIVY_MTDEV_DEVICE or similar.

            # Add the app's lib directory to PYTHONPATH so it can find its modules
            APP_LIB_PATH="$out/lib/python${pkgs.python3.pythonVersion}/site-packages"
            export PYTHONPATH="\$APP_LIB_PATH:\${PYTHONPATH:-}"

            echo "Launching NixOS MacroPad App..."
            echo "KIVY_HOME_PATH: \$KIVY_HOME_PATH"
            echo "KNOB_DEVICE_PATH: \$KNOB_DEVICE_PATH"
            echo "BUTTON_DEVICE_PATH: \$BUTTON_DEVICE_PATH"
            echo "PYTHONPATH: \$PYTHONPATH"
            # Execute the main Python script using the correct Python interpreter
            exec ${pkgs.python3}/bin/python3 \$APP_LIB_PATH/main_gui_app.py
            EOF
            chmod +x $out/bin/nixos-macropad-app-launcher
            runHook postInstall
          '';

          meta = with pkgs.lib; {
            description = "MacroPad GUI application for NixOS Superbird";
            homepage = "your-repo-link-here"; # Optional
            license = licenses.mit; # Or your chosen license
            mainProgram = "nixos-macropad-app-launcher"; # The wrapper script
          };
        };
      in
      {
        # Make the package available via `nix build .#nixos-macropad-app`
        packages.default = nixos-macropad-app-pkg;

        # NixOS configuration for the Superbird device
        nixosConfigurations.superbird = nixpkgs.lib.nixosSystem {
          system = "aarch64-linux"; # Or whatever nixos-superbird targets
          specialArgs = { inherit self pkgs; }; # Pass self and pkgs for convenience
          modules = [
            nixos-superbird.nixosModules.superbird # Import the base superbird module


            ({ config, pkgs, ... }: {
              imports = [

              ];


              options.hardware.macropad = {
                knobDevicePath = pkgs.lib.mkOption {
                  type = pkgs.lib.types.str;
                  default = "/dev/input/eventX";
                  description = "Path to the evdev device for the knob.";
                };
                buttonDevicePath = pkgs.lib.mkOption {
                  type = pkgs.lib.types.str;
                  default = "/dev/input/eventY";
                  description = "Path to the evdev device for the buttons.";
                };
              };

              # System packages needed for app and its environment
              environment.systemPackages = with pkgs; [
                nixos-macropad-app-pkg
                # Kivy runtime dependencies are in the app pkg, but ensure basics for Weston are there
                evtest # Useful for debugging input devices on the target
                bluez # For bluetooth
              ];

              # Configure superbird GUI to run your app
              superbird.gui = {
                enable = true; # Enable Weston (Wayland compositor)
                # app = "${nixos-macropad-app-pkg}/bin/nixos-macropad-app-launcher";
                # A more robust way to get the package:
                app = "${self.packages.${system}.default}/bin/nixos-macropad-app-launcher";
              };

              # Enable Bluetooth
              superbird.bluetooth = {
                enable = true;
                name = "NixMacroPad"; # Name broadcasted over Bluetooth
              };

              # Ensure user for app has permissions for evdev, and Kivy home is writable
              # By default, app launched by superbird.gui.app might run as root or a 'kiosk' user.
              # If it runs as root, /dev/input access is fine.
              # Writable directory for KIVY_HOME and config.json
              systemd.tmpfiles.rules = [
                "d /var/lib/nixos-macropad 0755 root root -" # Main app data dir
                "d /var/lib/nixos-macropad/kivy_home 0755 root root -" # Kivy config/cache
                # If your app needs to write config.json there:
                # "f /var/lib/nixos-macropad/config.json 0644 root root - default_config.json_or_empty"
              ];
              # If config.json is bundled with your app & app runs from read-only Nix store,
              # it must copy it to /var/lib/nixos-macropad/config.json on first run or use that path.
              # The ConfigManager in python currently uses "config.json" relative path.
              # This needs to be adjusted to an absolute writable path (e.g., /var/lib/nixos-macropad/config.json)
              # and the KIVY_HOME_PATH in the launcher script should point to the tmpfiles created path.


              # Ensure necessary kernel modules for input devices are loaded (usually handled by NixOS auto-detection)
              # boot.kernelModules = [ "evdev" ]; # Already default

              # Udev rules might be needed for input device permissions if not running as root
              # services.udev.extraRules = ''
              #   KERNEL=="event*", SUBSYSTEM=="input", ATTRS{name}=="Your Knob Name*", MODE="0660", GROUP="input"
              #   KERNEL=="event*", SUBSYSTEM=="input", ATTRS{name}=="Your Button Name*", MODE="0660", GROUP="input"
              # '';
              # users.users.your-app-user.extraGroups = [ "input" ]; # If app runs as specific user

              # Weston/Wayland configuration (usually defaults from superbird are fine)
              # services.weston.enable = true; # Handled by superbird.gui.enable

              # NixOS settings
              superbird.stateVersion = "0.2"; # From nixos-superbird template
              system.stateVersion = "24.05"; # Or your target NixOS version
            })
          ];
        };
      }
    );
}
