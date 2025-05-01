# nix/macro-pad-module.nix
{ config, pkgs, lib, specialArgs, ... }:

with lib;

let
  cfg = config.services.macroPadBackend;
  # Get the definition function from specialArgs
  backendDef = specialArgs.macro-pad-backend-def;
  # Evaluate the backend definition using the pkgs passed to *this module*
  backendPkg = backendDef { inherit pkgs; };
in
{
  options.services.macroPadBackend = {
    enable = mkEnableOption "NixOS Macro Pad Backend Service";

    package = mkOption {
      type = types.package;
      # Default to the package evaluated using this module's pkgs
      default = backendPkg;
      description = "The package providing the backend service.";
    };

    configFile = mkOption {
      type = types.str;
      default = "/var/lib/macro-pad/config.json";
      description = "Path to the configuration file for key mappings.";
    };
  };

  config = mkIf cfg.enable {
    # Ensure the directory for the config file exists and has correct permissions
    systemd.tmpfiles.rules = [
      "d /var/lib/macro-pad 0750 root root -"
      # Use mkForce because nixos-superbird might also try to manage this file/dir
      # Ensure the backend user/group can write if not root
      "f ${cfg.configFile} 0640 root root - '{}'"
    ];

    # Define the systemd service for the backend
    systemd.services.macro-pad-backend = {
      description = "NixOS Macro Pad Backend Service";
      after = [ "network.target" "bluetooth.service" "weston.service" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = "root"; # Consider a dedicated user later
        Group = "root";
        # Use cfg.package which now correctly defaults to the evaluated package
        ExecStart = ''
          ${cfg.package}/bin/macro-pad-backend \
            --config ${cfg.configFile}
        '';
        Restart = "on-failure";
        RestartSec = "5s";
        StandardOutput = "journal";
        StandardError = "journal";
      };
    };

    # Core dependencies should be in the package definition, but ensure bluez is present system-wide for D-Bus
    environment.systemPackages = [ pkgs.bluez pkgs.evtest ];

  };
}