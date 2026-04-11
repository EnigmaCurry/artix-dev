# artix-dev

Automated installer for [Artix Linux](https://artixlinux.org) with full
disk encryption (LUKS + LVM), the [dinit](https://davmac.org/projects/dinit/)
init system, and an optional [Sway](https://swaywm.org) Wayland desktop
managed by [Nix home-manager](https://github.com/nix-community/home-manager).

This is an unofficial community tool, not affiliated with the Artix Linux
project.

## Quick start

Boot the [Artix base dinit ISO](https://artixlinux.org/download.php).
Log in with the default credentials (`artix` / `artix`), then connect
to the network:

```bash
nmtui
```

Select **Activate a connection**, choose your WiFi SSID, enter the
password, then quit nmtui.

Sync the system clock (requires internet; takes less than a minute).
TLS will fail if the clock is too far off:

```bash
sudo ntpd -qg
```

#### Remote install via SSH (optional; recommended)

If you prefer to run the install from another machine (mouse support
in the TUI, easier to copy/paste, scroll back, etc.), enable SSH on
the live ISO:

```bash
passwd                        # set a password for the artix user
sudo dinitctl start sshd      # start the SSH server
ip a                          # note your IP address
```

Then SSH in from your other machine:

```bash
ssh artix@<ip-address>
```

#### Run the installer

```bash
curl -sLO https://github.com/EnigmaCurry/artix-dev/releases/download/latest/artix-dev.pyz
python artix-dev.pyz install
```

A TUI guides you through disk, encryption, system, SSH, and feature
configuration. When ready, press **Install** on the Review screen to begin.

After phase 1 completes, reboot (remove the USB after the machine
reinitializes). On first boot, log in and run:

```bash
artix-dev setup
```

This runs phase 2: system update, Podman, libvirt, Nix, Sway desktop,
sway-home dotfiles, and Flatpak. Reboot when finished.

## What it does

### Phase 1 — Live USB (install)

- GPT partitioning (ESP + LUKS partition)
- LUKS1 encryption (aes-xts-plain64 by default, configurable)
- LVM inside LUKS (volBoot, volSwap, volRoot)
- Base system via basestrap (kernel, dinit, cryptsetup, lvm2, grub,
  networkmanager)
- Chroot configuration: locale, timezone, hostname, mkinitcpio hooks,
  GRUB with `GRUB_ENABLE_CRYPTODISK`, user account, dinit services

### Phase 2 — First boot (setup)

- System update with mkinitcpio hook verification
- Rootless Podman (with userns for linux-hardened)
- QEMU/libvirt
- Nix (single-user, no daemon)
- Sway desktop (sway, foot, pipewire, xdg-portals, greetd/tuigreet)
- [sway-home](https://github.com/EnigmaCurry/sway-home) dotfiles via
  Nix home-manager
- Flatpak + Flathub

All features are optional and individually togglable in the TUI.

## Configuration

The TUI generates a TOML config file stored at
`/root/artix-dev/config.toml`. You can also write one by hand — see
[`examples/nvme-fde.toml`](examples/nvme-fde.toml) for the full schema
with defaults.

All TOML sections are optional; omitted sections use defaults. Passwords
(LUKS passphrase, root password, user password) are always prompted
interactively and never stored in config.

### Key options

| Section    | Field        | Default              | Notes                                       |
|------------|--------------|----------------------|---------------------------------------------|
| `disk`     | `device`     | —                    | Target disk (e.g. `/dev/nvme0n1`, `/dev/vda`)|
| `disk`     | `trim`       | `true`               | SSD TRIM support                            |
| `luks`     | `cipher`     | `aes-xts-plain64`   | Also: `serpent-xts-plain64`, `twofish-xts-plain64` |
| `luks`     | `key_size`   | `512`                | Bits (256 or 512)                           |
| `system`   | `kernel`     | `linux-hardened`     | Also: `linux`, `linux-lts`, `linux-zen`     |
| `system`   | `hostname`   | `artix`              |                                             |
| `system`   | `ssh`        | `disable`            | Also: `password`, `keys_only`               |
| `features` | `enable`     | all enabled          | `desktop`, `nix`, `sway_home`, `podman`, `flatpak` |

## Requirements

- Artix Linux base dinit live ISO
- UEFI firmware
- Network connectivity
- A target disk (all data will be destroyed)

## Development

```bash
just test              # run tests
uv run pytest tests/test_config.py::test_name -v   # single test
just build             # build .pyz zipapp
```
