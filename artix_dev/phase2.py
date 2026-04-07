"""Phase 2: Post-install setup — idempotent steps run on first boot."""

from __future__ import annotations

import os
import subprocess

from artix_dev.config import InstallConfig, Kernel, SshPolicy
from artix_dev.run import (
    append_file,
    die,
    heading,
    makedirs,
    run,
    run_as_user,
    run_output,
    run_shell,
    symlink,
    write_file,
)


# --- Helpers ---

def _pkg_installed(pkg: str) -> bool:
    """Check if a pacman package is installed."""
    from artix_dev.run import DRY_RUN
    if DRY_RUN:
        return False  # assume not installed in dry-run
    result = subprocess.run(
        ["pacman", "-Q", pkg], capture_output=True,
    )
    return result.returncode == 0


def _service_enabled(name: str) -> bool:
    """Check if a dinit service is enabled (symlinked in boot.d)."""
    from artix_dev.run import DRY_RUN
    if DRY_RUN:
        return False
    return os.path.islink(f"/etc/dinit.d/boot.d/{name}")


def _file_contains(path: str, text: str) -> bool:
    """Check if a file contains a string."""
    from artix_dev.run import DRY_RUN
    if DRY_RUN:
        return False
    try:
        return text in open(path).read()
    except OSError:
        return False


def _path_exists(path: str) -> bool:
    from artix_dev.run import DRY_RUN
    if DRY_RUN:
        return False
    return os.path.exists(path)


def _is_link(path: str) -> bool:
    from artix_dev.run import DRY_RUN
    if DRY_RUN:
        return False
    return os.path.islink(path)


def _is_dir(path: str) -> bool:
    from artix_dev.run import DRY_RUN
    if DRY_RUN:
        return False
    return os.path.isdir(path)


def _user_home(username: str) -> str:
    return os.path.expanduser(f"~{username}")


# --- Steps ---

def system_update(cfg: InstallConfig) -> None:
    heading("System update")
    run("pacman", "-Syu", "--noconfirm")

    # Verify mkinitcpio hooks survived the upgrade
    hooks_ok = _file_contains("/etc/mkinitcpio.conf", "encrypt")
    if not hooks_ok:
        print("WARNING: mkinitcpio hooks missing 'encrypt', re-adding...")
        hooks = (
            "HOOKS=(base udev autodetect microcode modconf block "
            "encrypt keyboard keymap consolefont lvm2 resume filesystems fsck)"
        )
        run_shell(
            f"sed -i 's/^HOOKS=.*/{hooks}/' /etc/mkinitcpio.conf"
        )
        run("mkinitcpio", "-p", cfg.kernel_package)
    else:
        print("  mkinitcpio hooks OK.")


def setup_podman(cfg: InstallConfig) -> None:
    if not cfg.install_podman:
        return
    heading("Setting up rootless Podman")
    username = cfg.system.username

    if not _pkg_installed("podman"):
        run("pacman", "-S", "--noconfirm",
            "podman", "crun", "slirp4netns", "fuse-overlayfs")

    # subuid/subgid
    subuid_file = "/etc/subuid"
    if not _file_contains(subuid_file, username):
        run("usermod",
            "--add-subuids", "100000-165535",
            "--add-subgids", "100000-165535",
            username)

    # userns for linux-hardened
    if cfg.system.kernel == Kernel.HARDENED:
        sysctl_conf = "/etc/sysctl.d/userns.conf"
        if not _path_exists(sysctl_conf):
            makedirs("/etc/sysctl.d", exist_ok=True)
            write_file(sysctl_conf, "kernel.unprivileged_userns_clone=1\n")
            run("sysctl", "-w", "kernel.unprivileged_userns_clone=1")
        else:
            print("  userns sysctl already configured.")
    else:
        print("  Skipping userns sysctl (not linux-hardened).")


def setup_libvirt(cfg: InstallConfig) -> None:
    if not cfg.install_libvirt:
        return
    heading("Setting up QEMU/libvirt")

    if not _pkg_installed("qemu-full"):
        run("pacman", "-S", "--noconfirm",
            "qemu-full", "virt-manager", "libvirt", "libvirt-dinit",
            "dnsmasq", "edk2-ovmf")

    if not _service_enabled("libvirtd"):
        run("dinitctl", "enable", "libvirtd")
    run("dinitctl", "start", "libvirtd")


def setup_nix(cfg: InstallConfig) -> None:
    if not cfg.install_nix:
        return
    heading("Installing Nix package manager")
    username = cfg.system.username
    home = _user_home(username)

    if _path_exists(f"{home}/.nix-profile/bin/nix"):
        print("  Nix already installed.")
    else:
        # Create /nix owned by user (nix single-user install expects this)
        if not _path_exists("/nix"):
            makedirs("/nix", mode=0o755, exist_ok=True)
            run("chown", username, "/nix")
        run_as_user(username,
                    "curl", "-L", "https://nixos.org/nix/install",
                    "|", "sh", "-s", "--", "--no-daemon")

    # Make nix available for all login sessions
    nix_profile_link = "/etc/profile.d/nix.sh"
    nix_profile_target = f"{home}/.nix-profile/etc/profile.d/nix.sh"
    if not _is_link(nix_profile_link):
        if _path_exists(nix_profile_target):
            symlink(nix_profile_target, nix_profile_link)
        else:
            print(f"  WARNING: {nix_profile_target} not found, skipping profile.d link")


def setup_desktop(cfg: InstallConfig) -> None:
    if not cfg.install_desktop:
        return
    heading("Installing desktop packages (sway, audio, greetd)")

    # Sway and friends
    sway_pkgs = [
        "sway", "xorg-xwayland", "dunst", "libnotify",
        "lxsession", "ttf-font-awesome",
    ]
    audio_pkgs = [
        "pipewire", "pipewire-pulse", "wireplumber",
        "pavucontrol", "sof-firmware",
        "pipewire-dinit", "wireplumber-dinit",
    ]
    portal_pkgs = [
        "xdg-desktop-portal", "xdg-desktop-portal-gtk",
        "xdg-desktop-portal-wlr",
    ]

    missing = [p for p in sway_pkgs + audio_pkgs + portal_pkgs
               if not _pkg_installed(p)]
    if missing:
        run("pacman", "-S", "--noconfirm", *missing)
    else:
        print("  Desktop packages already installed.")

    # greetd + tuigreet
    if not _pkg_installed("greetd"):
        run("pacman", "-S", "--noconfirm",
            "greetd", "greetd-tuigreet", "greetd-dinit")

    # greetd config
    greetd_config = "/etc/greetd/config.toml"
    if not _file_contains(greetd_config, "tuigreet"):
        write_file(greetd_config,
                    '[terminal]\nvt = 7\n\n'
                    '[default_session]\n'
                    'command = "tuigreet --time --remember --remember-session '
                    '--sessions /usr/share/wayland-sessions"\n'
                    'user = "greeter"\n')

    # Sway desktop entry
    desktop_entry = "/usr/share/wayland-sessions/sway.desktop"
    if not _path_exists(desktop_entry):
        makedirs("/usr/share/wayland-sessions", exist_ok=True)
        write_file(desktop_entry,
                    "[Desktop Entry]\n"
                    "Name=Sway\n"
                    "Exec=bash --login -c sway\n"
                    "Type=Application\n")

    # Enable greetd
    if not _service_enabled("greetd"):
        run("dinitctl", "enable", "greetd")

    # pipewire-pulse user dinit service
    pp_service = "/etc/dinit.d/user/pipewire-pulse"
    if not _path_exists(pp_service):
        write_file(pp_service,
                    "type = process\n"
                    "command = /usr/bin/pipewire-pulse\n"
                    "depends-on = pipewire\n")


def setup_user_dinit(cfg: InstallConfig) -> None:
    if not cfg.install_desktop:
        return
    heading("Configuring user-level dinit for PipeWire")
    username = cfg.system.username
    home = _user_home(username)

    dinit_dir = f"{home}/.config/dinit.d"
    boot_dir = f"{dinit_dir}/boot.d"
    makedirs(boot_dir, exist_ok=True)

    # Boot service
    boot_file = f"{dinit_dir}/boot"
    if not _path_exists(boot_file):
        write_file(boot_file,
                    "type = internal\n"
                    "waits-for.d = boot.d\n")

    # Symlinks for user services
    user_services = {
        "dbus": "/etc/dinit.d/user/dbus",
        "pipewire": "/etc/dinit.d/user/pipewire",
        "wireplumber": "/etc/dinit.d/user/wireplumber",
        "pipewire-pulse": "/etc/dinit.d/user/pipewire-pulse",
    }
    for name, target in user_services.items():
        link = f"{boot_dir}/{name}"
        if not _is_link(link):
            symlink(target, link)

    # Fix ownership
    run("chown", "-R", f"{username}:{username}", f"{home}/.config/dinit.d")


def setup_sway_home(cfg: InstallConfig) -> None:
    if not cfg.install_sway_home:
        return
    heading("Installing sway-home")
    username = cfg.system.username
    home = _user_home(username)
    clone_path = cfg.sway_home.clone_path.replace("~", home)

    # git and just needed
    if not _pkg_installed("git"):
        run("pacman", "-S", "--noconfirm", "git", "just")

    # Backup existing dotfiles (only if originals haven't been backed up yet)
    if not _path_exists(f"{home}/.bashrc.orig") and _path_exists(f"{home}/.bashrc"):
        for f in [".config", ".bashrc", ".bash_profile"]:
            src = f"{home}/{f}"
            if _path_exists(src):
                run_as_user(username, "mv", src, f"{src}.orig")

    # Enable flakes
    nix_config_dir = f"{home}/.config/nix"
    makedirs(nix_config_dir, exist_ok=True)
    nix_conf = f"{nix_config_dir}/nix.conf"
    if not _file_contains(nix_conf, "flakes"):
        write_file(nix_conf, "experimental-features = nix-command flakes\n")

    # Clone repo
    if _is_dir(clone_path):
        print(f"  {clone_path} already exists, skipping clone.")
    else:
        clone_parent = os.path.dirname(clone_path)
        run_as_user(username, "mkdir", "-p", clone_parent)
        run_as_user(username,
                    "git", "clone", cfg.sway_home.repo, clone_path)

    # Run hm-install (idempotent — home-manager switch is safe to re-run)
    run_as_user(username,
                f"cd {clone_path} && just hm-install")

    # Fix ownership of nix config
    run("chown", "-R", f"{username}:{username}", f"{home}/.config")


def setup_flatpak(cfg: InstallConfig) -> None:
    if not cfg.install_flatpak:
        return
    heading("Setting up Flatpak")

    if not _pkg_installed("flatpak"):
        run("pacman", "-S", "--noconfirm", "flatpak")

    # Add flathub remote
    from artix_dev.run import DRY_RUN
    has_flathub = False
    if not DRY_RUN:
        result = subprocess.run(
            ["flatpak", "remote-list", "--columns=name"],
            capture_output=True, text=True,
        )
        has_flathub = "flathub" in result.stdout
    if not has_flathub:
        run("flatpak", "remote-add", "--if-not-exists",
            "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo")
    else:
        print("  Flathub remote already configured.")

    # Install apps
    for app in cfg.flatpak_apps:
        installed = False
        if not DRY_RUN:
            result = subprocess.run(
                ["flatpak", "info", app],
                capture_output=True,
            )
            installed = result.returncode == 0
        if not installed:
            run("flatpak", "install", "-y", "flathub", app)
        else:
            print(f"  {app} already installed.")


def run_phase2(cfg: InstallConfig, dry_run: bool = False) -> None:
    """Execute Phase 2 post-install setup. Idempotent and resumable."""
    import artix_dev.run as run_mod
    run_mod.DRY_RUN = dry_run

    if not dry_run and os.geteuid() != 0:
        die("Phase 2 must be run as root (use sudo)")

    errors = cfg.validate()
    if errors:
        for err in errors:
            print(f"Config error: {err}")
        die("Fix config errors before running setup")

    system_update(cfg)
    setup_podman(cfg)
    setup_libvirt(cfg)
    setup_nix(cfg)
    setup_desktop(cfg)
    setup_user_dinit(cfg)
    setup_sway_home(cfg)
    setup_flatpak(cfg)

    # Remove phase 1 MOTD
    if _path_exists("/etc/motd"):
        run("rm", "/etc/motd")

    heading("Phase 2 complete")
    print("Log out and back in to pick up all changes.")
    print("If greetd was installed, it will be available on next boot.")
