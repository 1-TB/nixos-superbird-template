{
  description = "NixOS Superbird configuration for Macro Pad";

  inputs = {
    nixos-superbird.url = "github:joeyeamigh/nixos-superbird/main";
    nixpkgs.follows = "nixos-superbird/nixpkgs";
  };

  outputs =
    {
      self,
      nixpkgs,
      nixos-superbird,
    }:
    let
      targetSystem = "aarch64-linux";
      # Import the backend package *definition function* (not evaluated yet)
      macro-pad-backend-def = import ./nix/backend-package.nix;
    in
    {
      # Define the NixOS configuration directly
      nixosConfigurations.superbird = nixpkgs.lib.nixosSystem {
        system = targetSystem;
        specialArgs = {
          inherit self;
          # Pass the definition function to the module system
          macro-pad-backend-def = macro-pad-backend-def;
          # pkgs is now provided implicitly by nixosSystem
        };
        modules = [
          nixos-superbird.nixosModules.superbird
          ./nix/macro-pad-module.nix # Our custom module definition
          ( # Inline configuration block
            { config, pkgs, ... }:
            {
              system.stateVersion = "24.11";
              superbird.stateVersion = "0.2";
              # superbird.installer.manualScript = true; # Uncomment if needed
              superbird.name = "NixOS MacroPad";
              superbird.version = "0.1.0";
              superbird.description = "A custom macro pad running on NixOS";
              superbird.bluetooth = {
                enable = true;
                name = "NixOS MacroPad";
              };
              superbird.gui = {
                enable = true;
                kiosk_url = "http://localhost:5000";
              };
              networking.firewall.enable = false;
              networking.useDHCP = false;
              environment.systemPackages = [ pkgs.python3 pkgs.git pkgs.chromium ];

              # User settings
              users.users.root.extraGroups = [ "input" ];
              users.users.weston.extraGroups = [ "input" ]; # Existing setting

              users.users.weston.isSystemUser = true; # Define user type
              users.users.weston.group = "weston";    # Define primary group
              users.groups.weston = {};               # Define the 'weston' group
            }
          )
        ];
      }; # End nixosConfigurations

      # Define packages - get pkgs from the evaluated NixOS configuration
      packages = let
        # Get the actual pkgs instance used by the nixos configuration above
        pkgsForTarget = self.nixosConfigurations.superbird.pkgs;
      in {
        # Attribute set for the target system
        ${targetSystem} = {
           # Evaluate the backend definition using the config's pkgs
           macro-pad-backend = macro-pad-backend-def { pkgs = pkgsForTarget; };
           # Get the installer derivation from the config result
           installer = self.nixosConfigurations.superbird.config.system.build.installer;
           # Set the default package for convenience
           default = self.packages.${targetSystem}.installer;
        };
        # You could add packages for other systems here if needed
        # x86_64-linux = { ... };
      }; # End packages

      # Define other outputs like devShells if needed
      # devShells = { ... };

    }; # End outputs

} # End of top-level flake attribute set