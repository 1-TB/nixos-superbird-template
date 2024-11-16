# nixos-superbird-template

A flake template for [`nixos-superbird`](https://github.com/JoeyEamigh/nixos-superbird). Many helpful commands exist in the [`Justfile`](./Justfile).

For documentation about what is going on here, visit <https://github.com/JoeyEamigh/nixos-superbird>.

Whenever there is a new update to `nixos-superbird`, you must run `nix flake update` (or `rm flake.nix` if using docker) to get the newest version.

## Build Installer (docker)

without build caching:

```sh
docker run --privileged --rm -it -v $(pwd):/workdir ghcr.io/joeyeamigh/nixos-superbird/builder:latest
```

with build caching:

```sh
docker volume create nix-store
docker volume create nix-root
docker run --privileged --rm -it \
  -v ./:/workdir \
  -v nix-store:/nix \
  -v nix-root:/root \
  ghcr.io/joeyeamigh/nixos-superbird/builder:latest
```

or all-in-one:

```sh
docker compose up
```

### MacOS Notes

On MacOS, [there is a bug that prevents filesystem permissions from working properly](https://github.com/docker/for-mac/issues/6243). Until this is fixed, a workaround is to go into the Docker Desktop settings, scroll down to Virtual Machine Options, and select `osxfs (Legacy)` as the file sharing implementation.

<!-- MacOS does not use uid/gid 1000:1000 like Linux does. To make sure permissions work, run the Docker commands with the environment variable `SUPERBIRD_CHOWN` set to your user and group. You can see your user and primary group (usually `staff`) by running the `id` command.

For example:

```sh
docker run -e SUPERBIRD_CHOWN='501:20' --privileged --rm -it -v $(pwd):/workdir ghcr.io/joeyeamigh/nixos-superbird/builder:latest
``` -->

## Build Installer (local)

```sh
nix build '.#nixosConfigurations.superbird.config.system.build.installer' -j$(nproc) --show-trace
echo "kernel is $(stat -Lc%s -- result/linux/kernel | numfmt --to=iec)"
echo "initrd is $(stat -Lc%s -- result/linux/initrd.img | numfmt --to=iec)"
echo "rootfs (sparse) is $(stat -Lc%s -- result/linux/rootfs.img | numfmt --to=iec)"

sudo rm -rf ./out
mkdir ./out
cp -r ./result/* ./out/
chown -R $(whoami):$(whoami) ./out
cd ./out

sudo ./scripts/shrink-img.sh
echo "rootfs (compact) is $(stat -Lc%s -- ./linux/rootfs.img | numfmt --to=iec)"
```

## Run Installer

```sh
cd out

./install.sh
```

## Push System Over SSH (Development)

If you are planning on building multiple iterations of the system, build the installer using the following command:

```sh
docker run --privileged -it -v $(pwd):/workdir ghcr.io/joeyeamigh/nixos-superbird/builder:latest
```

Then, after flashing the device, bring your network interface online by running `cd ./out && ./scripts/ssh.sh`. Then you can run the Docker container with host networking, and push any changes directly.

```sh
docker run --privileged --network=host --entrypoint bash -it -v ./:/workdir ghcr.io/joeyeamigh/nixos-superbird/builder:latest
```

In the container:

```sh
nix run github:serokell/deploy-rs
```
