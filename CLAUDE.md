# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

artix-dev automates the installation of Artix Linux (Arch-based, no systemd) with full disk encryption, dinit init system, and a sway Wayland desktop managed by Nix home-manager. It wraps the manual process documented in the [blog post](../blog.rymcg.tech/content/blog/linux/artix-linux-fde-dinit.md) into a config-driven Python tool.

The installation is TOML-configured and split into two phases:

**Phase 1 — From live USB (as root):**
- Disk partitioning (GPT: 1GB ESP + LUKS partition)
- LUKS encryption (serpent-xts-plain64, luks1 for GRUB compatibility)
- LVM inside LUKS (volBoot, volSwap, volRoot)
- basestrap package installation (kernel, dinit, cryptsetup, lvm2, grub, networkmanager, openssh)
- System configuration in chroot: locale, timezone, hostname, mkinitcpio hooks (`encrypt`, `lvm2`, `resume`), GRUB with `GRUB_ENABLE_CRYPTODISK`, user account, dinit service symlinks, caps lock remap

**Phase 2 — On first boot (as user):**
- Podman (rootless, with userns enabled for linux-hardened)
- QEMU/libvirt
- Nix (single-user, no daemon)
- Sway desktop (sway, pipewire, xdg-portals, greetd/tuigreet)
- sway-home (dotfiles via Nix home-manager)
- Flatpak + Flathub

## Commands

```bash
just test          # run tests (uses uv)
```

Run a single test:
```bash
uv run pytest tests/test_config.py::test_name -v
```

## Key Design Details

- **Config dataclass** (`artix_dev/config.py`): `InstallConfig` is the root, composed of `DiskConfig`, `LuksConfig`, `LvmConfig`, `SystemConfig`, `SwayHomeConfig`, plus `Feature` and `OptionalService` enum sets. Round-trips to/from TOML. All TOML sections are optional (omitted = defaults).
- **Feature implications**: `SWAY_HOME` implies `NIX` and `DESKTOP` via properties, not by mutating the feature set. Check `install_*` properties, not `features` directly, when deciding what to install.
- **Partition naming**: `DiskConfig.part_prefix` handles the NVMe `p` separator (`nvme0n1p1`) vs SATA/virtio (`vda1`). Partition paths are derived properties, never stored.
- **Passwords**: LUKS passphrase, root password, and user password are intentionally excluded from config — they must be prompted interactively.
- **Dinit services**: Enabled via direct symlinks into `/etc/dinit.d/boot.d/` (not `dinitctl --offline enable`, which is broken on the 20260402 ISO).
- **Kernel**: Configurable via `Kernel` enum (hardened, standard, lts, zen). Defaults to `linux-hardened`. The `kernel_package` and `kernel_headers_package` properties derive package names.
- **LUKS**: Must use `luks1` (not luks2) because GRUB's luks2 support is limited and cannot decrypt an encrypted `/boot` with luks2.
- **mkinitcpio HOOKS order matters**: `encrypt` must come before `lvm2`, `keyboard` before `encrypt`, `resume` after `lvm2`.
- **GRUB**: Installed twice — once as `--bootloader-id=artix` and once as `--removable` (fallback for firmware that ignores EFI boot entries).

## Examples

`examples/nvme-fde.toml` — full default config for NVMe FDE setup. Users copy and edit this.
