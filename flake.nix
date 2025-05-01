{
  description = "NixOS Superbird configuration for Macro Pad";

  inputs = {
    nixos-superbird.url = "github:joeyeamigh/nixos-superbird/main";
    nixpkgs.follows = "nixos-superbird/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      nixos-superbird,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        inherit (nixpkgs.lib) nixosSystem optionalAttrs;

        # Import our custom backend package definition
        macro-pad-backend-pkg = import ./nix/backend-package.nix { inherit pkgs; };

      in
      {
        nixosConfigurations = {
          superbird = nixosSystem {
            system = "aarch64-linux"; # Target system for Car Thing
            specialArgs = { inherit self pkgs macro-pad-backend-pkg; }; # Pass package to modules
            modules = [
              nixos-superbird.nixosModules.superbird
              ./nix/macro-pad-module.nix # Our custom module
              (
                { config, pkgs, ... }:
                {
                  # Basic NixOS settings
                  system.stateVersion = "24.11"; # Or your preferred version
                  superbird.stateVersion = "0.2"; # Match nixos-superbird version used

                  # Force manual install script for now if needed
                  # superbird.installer.manualScript = true;

                  # Configure Superbird base settings
                  superbird.name = "NixOS MacroPad";
                  superbird.version = "0.1.0";
                  superbird.description = "A custom macro pad running on NixOS";

                  superbird.bluetooth = {
                    enable = true;
                    name = "NixOS MacroPad";
                  };

                  # Use the webapp option pointing to our backend service
                  superbird.gui = {
                    enable = true;
                    # Point kiosk mode to the local web server run by our backend
                    kiosk_url = "http://localhost:5000"; # Default Flask port
                    # Ensure Chromium is available if not pulled in by kiosk_url automatically
                    environment.systemPackages = [ pkgs.chromium ];
                  };

                  # Networking over USB
                  networking.firewall.enable = false; # Keep it simple for local dev
                  networking.useDHCP = false; # superbird sets up its own networking

                  # Ensure Python and necessary tools are available if needed globally
                  # (dependencies should ideally be handled by the package)
                  environment.systemPackages = [ pkgs.python3 pkgs.git ];

                  # Add user groups needed (e.g., input for evdev)
                  users.users.root.extraGroups = [ "input" ];
                  users.users.weston.extraGroups = [ "input" ]; # If Weston runs apps needing input
                }
              )
            ];
          };
        };

        # Allow building the backend package independently if needed
        packages = {
          macro-pad-backend = macro-pad-backend-pkg;
        };

        # Add devShell later if needed for development
        # devShells.default = pkgs.mkShell { ... };

      }
    );
}