# nixos-superbird-template

A flake template for [`nixos-superbird`](https://github.com/JoeyEamigh/nixos-superbird). Many helpful commands exist in the [`Justfile`](./Justfile).

For documentation about what is going on here, visit <https://github.com/JoeyEamigh/nixos-superbird>.

## Build Installer (docker)

without build caching:

```sh
docker run --privileged --rm -it -v ./:/workdir ghcr.io/joeyeaimgh/nixos-superbird/builder:latest
```

with build caching:

```sh
docker volume create nix-store
docker volume create nix-root
docker run --privileged --rm -it \
  -v ./:/workdir \
  -v nix-store:/nix \
  -v nix-root:/root \
  ghcr.io/joeyeaimgh/nixos-superbird/builder:latest
```

or all-in-one:

```sh
docker compose up
```

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

## Push System Over SSH

```sh
nix run github:serokell/deploy-rs
```
