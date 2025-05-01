outputs =
    {
      self,
      nixpkgs,
      nixos-superbird,
    }:
    let
      targetSystem = "aarch64-linux";
      pkgs_aarch64 = nixpkgs.legacyPackages.${targetSystem};
      macro-pad-backend-pkg = import ./nix/backend-package.nix { pkgs = pkgs_aarch64; };
    in
    {
      # Define the NixOS configuration directly
      nixosConfigurations.superbird = nixpkgs.lib.nixosSystem {
        system = targetSystem;
        specialArgs = {
          inherit self;
          pkgs = pkgs_aarch64;
          macro-pad-backend-pkg = macro-pad-backend-pkg;
        };
        modules = [
          nixos-superbird.nixosModules.superbird
          ./nix/macro-pad-module.nix # Our custom module
          ( # Configuration previously in the flake.nix inline block
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
                environment.systemPackages = [ pkgs.chromium ];
              };
              networking.firewall.enable = false;
              networking.useDHCP = false;
              environment.systemPackages = [ pkgs.python3 pkgs.git ];
              users.users.root.extraGroups = [ "input" ];
              users.users.weston.extraGroups = [ "input" ];
            }
          )
        ];
      }; # End nixosConfigurations

      # --- Corrected Packages Definition ---
      packages = {
        # Attribute set for the target system
        ${targetSystem} = {
           # Packages for aarch64-linux defined *inside* this set
           macro-pad-backend = macro-pad-backend-pkg;
           installer = self.nixosConfigurations.superbird.config.system.build.installer;
           default = self.packages.${targetSystem}.installer; # Use self to reference within outputs
        };

      }; # End packages


    };