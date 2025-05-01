# This file defines the Nix package for the Python backend service.
{ pkgs ? import <nixpkgs> {} }:

pkgs.python3Packages.buildPythonApplication {
  pname = "nixos-macro-pad-backend";
  version = "0.1.0";

  # Location of the Python source code relative to the flake root
  src = ../backend;

  # Runtime dependencies needed by the Python code
  propagatedBuildInputs = with pkgs.python3Packages; [
    flask # For the web UI and API
    evdev # For reading input devices
    dbus-python # For BlueZ D-Bus communication
    # Add other Python libraries if needed (e.g., requests, pyserial)
  ];

  # Command to make the main script executable
  postInstall = ''
    install -Dm755 $src/main.py $out/bin/macro-pad-backend
    # Copy other necessary files if any (e.g., static assets if not handled by Flask)
  '';

  # Check phase can be added if you write tests
  # doCheck = true;
  # checkInputs = [ pytest ];
  # checkPhase = ''
  #   pytest
  # '';

  meta = with pkgs.lib; {
    description = "Backend service for the NixOS Macro Pad";
    homepage = "local"; # Replace with actual URL if hosted
    license = licenses.mit; # Choose your license
    maintainers = [ maintainers.your_github_username ]; # Optional
  };
}