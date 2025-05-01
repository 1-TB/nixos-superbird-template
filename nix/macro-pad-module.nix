# This module configures the macro pad specific services and settings
{ config, pkgs, lib, specialArgs, ... }:

with lib;

let
  cfg = config.services.macroPadBackend;
  backendPkg = specialArgs.macro-pad-backend-pkg; # Get the package from specialArgs
in
{
  options.services.macroPadBackend = {
    enable = mkEnableOption "NixOS Macro Pad Backend Service";

    package = mkOption {
      type = types.package;
      default = backendPkg;
      description = "The package providing the backend service.";
    };

    configFile = mkOption {
      type = types.str;
      default = "/var/lib/macro-pad/config.json";
      description = "Path to the configuration file for key mappings.";
    };

    # Add options for device paths if needed, or rely on backend discovery/config
    # knobDevice = mkOption { type = types.str; default = "/dev/input/eventX"; };
    # buttonDevice = mkOption { type = types.str; default = "/dev/input/eventY"; };
  };

  config = mkIf cfg.enable {
    # Ensure the directory for the config file exists and has correct permissions
    systemd.tmpfiles.rules = [
      "d /var/lib/macro-pad 0750 root root -"
      "f ${cfg.configFile} 0640 root root - '{}'" # Create empty config if missing
    ];

    # Define the systemd service for the backend
    systemd.services.macro-pad-backend = {
      description = "NixOS Macro Pad Backend Service";
      after = [ "network.target" "bluetooth.service" "weston.service" ]; # Depend on Bluetooth and Weston
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = "root"; # Running as root for input device access and BlueZ D-Bus potentially
        Group = "root";
        # Pass the config file path and any other necessary args/env vars
        ExecStart = ''
          ${cfg.package}/bin/macro-pad-backend \
            --config ${cfg.configFile}
        '';
        Restart = "on-failure";
        RestartSec = "5s";

        # Environment variables if needed by the backend
        # Environment = [ "EXAMPLE_VAR=value" ];

        # Standard output and error logging
        StandardOutput = "journal";
        StandardError = "journal";
      };
    };

    # Ensure necessary packages for the service are available
    # (These should be handled by the backend package definition itself,
    # but listing core dependencies here can sometimes help clarity)
    environment.systemPackages = [
      pkgs.bluez # Needed for Bluetooth D-Bus interfaces
      pkgs.python3 # Core dependency
      # Add evtest here if you want it easily available for debugging on the device
      pkgs.evtest
    ];

    # Add udev rules if specific device permissions are needed beyond 'input' group
    # services.udev.extraRules = ''
    #   KERNEL=="event*", SUBSYSTEM=="input", ATTRS{name}=="Your Knob Name", MODE="0660", GROUP="input"
    # '';
  };
}