"""Phase 1: Live USB installation — disk, encryption, base system, chroot config."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from artix_dev.config import InstallConfig, OptionalService, SshPolicy
from artix_dev.run import (
    DRY_RUN,
    append_file,
    die,
    heading,
    makedirs,
    run,
    run_chroot,
    run_shell,
    symlink,
    write_file,
)

OPTIONAL_SERVICE_PACKAGES: dict[OptionalService, list[str]] = {
    OptionalService.NTPD: ["openntpd", "openntpd-dinit"],
    OptionalService.SYSLOG: ["syslog-ng", "syslog-ng-dinit"],
    OptionalService.ACPID: ["acpid", "acpid-dinit"],
    OptionalService.CRONIE: ["cronie", "cronie-dinit"],
}

OPTIONAL_SERVICE_NAMES: dict[OptionalService, str] = {
    OptionalService.NTPD: "ntpd",
    OptionalService.SYSLOG: "syslog-ng",
    OptionalService.ACPID: "acpid",
    OptionalService.CRONIE: "cronie",
}


def install_live_deps() -> None:
    heading("Installing live environment dependencies")
    run("pacman", "-Sy", "--noconfirm",
        "gptfdisk", "parted", "cryptsetup", "lvm2", "dosfstools")


def partition_disk(cfg: InstallConfig) -> None:
    heading("Partitioning disk")
    disk = cfg.disk.device
    esp_size = cfg.disk.esp_size

    # Wipe
    run("sgdisk", "--zap-all", disk)
    if cfg.disk.trim:
        run("blkdiscard", disk)

    # Create GPT and partitions
    run("parted", "-s", disk, "mklabel", "gpt")
    run("parted", "-s", "-a", "optimal", disk,
        "mkpart", "ESP", "fat32", "0%", esp_size)
    run("parted", "-s", disk, "set", "1", "esp", "on")
    run("parted", "-s", "-a", "optimal", disk,
        "mkpart", "LUKS", "ext4", esp_size, "100%")
    run("parted", "-s", disk, "set", "2", "lvm", "on")
    run("parted", "-s", disk, "print")


def setup_luks(cfg: InstallConfig) -> None:
    heading("Setting up LUKS encryption")
    luks = cfg.luks
    part = cfg.disk.luks_partition

    run("cryptsetup", "benchmark")
    print("\n  Enter a secure passphrase for disk encryption.")
    print("  You will be prompted to enter it twice for verification.\n")
    run("cryptsetup",
        "--batch-mode",
        "--verbose",
        "--type", luks.luks_type,
        "--cipher", luks.cipher,
        "--key-size", str(luks.key_size),
        "--hash", luks.hash,
        "--iter-time", str(luks.iter_time),
        "--use-random",
        "--verify-passphrase",
        "luksFormat", part)
    run("cryptsetup", "luksOpen", part, "lvm-system")


def setup_lvm(cfg: InstallConfig) -> None:
    heading("Setting up LVM")
    lvm = cfg.lvm

    run("pvcreate", "/dev/mapper/lvm-system")
    run("vgcreate", "lvmSystem", "/dev/mapper/lvm-system")
    run("lvcreate", "--contiguous", "y", "--size", lvm.boot_size,
        "lvmSystem", "--name", "volBoot")
    if cfg.lvm.swap_enabled:
        run("lvcreate", "--contiguous", "y", "--size", lvm.swap_size,
            "lvmSystem", "--name", "volSwap")
    run("lvcreate", "--contiguous", "y", "--extents", "+100%FREE",
        "lvmSystem", "--name", "volRoot")


def format_partitions(cfg: InstallConfig) -> None:
    heading("Formatting partitions")
    run("mkfs.fat", "-F32", "-n", "ESP", cfg.disk.esp_partition)
    run("mkfs.ext4", "-L", "BOOT", "/dev/lvmSystem/volBoot")
    if cfg.lvm.swap_enabled:
        run("mkswap", "-L", "SWAP", "/dev/lvmSystem/volSwap")
    run("mkfs.ext4", "-L", "ROOT", "/dev/lvmSystem/volRoot")


def mount_partitions(cfg: InstallConfig) -> None:
    heading("Mounting partitions")
    if cfg.lvm.swap_enabled:
        run("swapon", "/dev/lvmSystem/volSwap")
    run("mount", "/dev/lvmSystem/volRoot", "/mnt")
    makedirs("/mnt/boot", exist_ok=True)
    run("mount", "/dev/lvmSystem/volBoot", "/mnt/boot")
    makedirs("/mnt/boot/efi", exist_ok=True)
    run("mount", cfg.disk.esp_partition, "/mnt/boot/efi")


def install_base(cfg: InstallConfig) -> None:
    heading("Installing base system")
    kernel = cfg.kernel_package
    headers = cfg.kernel_headers_package

    run("basestrap", "/mnt",
        "base", "base-devel", "dinit", "elogind-dinit")
    run("basestrap", "/mnt",
        kernel, headers, "linux-firmware")
    run("basestrap", "/mnt",
        "lvm2", "lvm2-dinit", "cryptsetup", "cryptsetup-dinit",
        "device-mapper-dinit")
    run("basestrap", "/mnt",
        "grub", "efibootmgr", "dosfstools")
    run("basestrap", "/mnt",
        "networkmanager", "networkmanager-dinit")
    run("basestrap", "/mnt",
        "openssh", "openssh-dinit")
    run("basestrap", "/mnt", "python", "nano", "vi", "less")


def copy_wifi_config() -> None:
    heading("Copying WiFi configuration")
    src = "/etc/NetworkManager/system-connections"
    if not DRY_RUN and (not os.path.isdir(src) or not os.listdir(src)):
        print("  No WiFi connections found, skipping.")
        return
    run("cp", "-r", src, "/mnt/etc/NetworkManager/")


def generate_fstab(cfg: InstallConfig) -> None:
    heading("Generating fstab")
    run_shell("fstabgen -U /mnt >> /mnt/etc/fstab")

    if cfg.disk.trim:
        run_shell('sed -i "s/relatime/relatime,discard/g" /mnt/etc/fstab')

    tmpfs_line = (
        f"tmpfs    /tmp    tmpfs    "
        f"rw,nosuid,nodev,relatime,size={cfg.system.tmpfs_size},mode=1777"
        f"    0 0\n"
    )
    append_file("/mnt/etc/fstab", tmpfs_line)


def chroot_set_root_password() -> None:
    heading("Setting root password")
    run_chroot("passwd")


def chroot_init_keyring() -> None:
    heading("Initializing pacman keyring")
    run_chroot("pacman", "-Sy", "--noconfirm")
    run_chroot("pacman-key", "--init")
    run_chroot("pacman-key", "--populate", "artix")


def chroot_configure_locale(cfg: InstallConfig) -> None:
    heading("Configuring locale")
    locale = cfg.system.locale
    append_file("/mnt/etc/locale.gen", f"{locale} UTF-8\n")
    run_chroot("locale-gen")
    lang = locale.split()[0] if " " in locale else locale
    write_file("/mnt/etc/locale.conf", f"LANG={lang}\n")


def chroot_configure_timezone(cfg: InstallConfig) -> None:
    heading("Configuring timezone")
    tz = cfg.system.timezone
    run_chroot("ln", "-sf", f"/usr/share/zoneinfo/{tz}", "/etc/localtime")
    run_chroot("hwclock", "--systohc")


def chroot_configure_hostname(cfg: InstallConfig) -> None:
    heading("Setting hostname")
    write_file("/mnt/etc/hostname", f"{cfg.system.hostname}\n")


def chroot_configure_capslock(cfg: InstallConfig) -> None:
    if not cfg.system.caps_lock_remap:
        return
    heading("Remapping Caps Lock to Control")
    # Console/TTY
    write_file(
        "/mnt/usr/share/kbd/keymaps/personal.map",
        'include "/usr/share/kbd/keymaps/i386/qwerty/us.map.gz"\n'
        "keycode 58 = Control\n",
    )
    write_file("/mnt/etc/vconsole.conf", "KEYMAP=personal\n")
    # X11
    makedirs("/mnt/etc/X11/xorg.conf.d", exist_ok=True)
    write_file(
        "/mnt/etc/X11/xorg.conf.d/00-keyboard.conf",
        'Section "InputClass"\n'
        '    Identifier "system-keyboard"\n'
        '    MatchIsKeyboard "on"\n'
        '    Option "XkbLayout" "us"\n'
        '    Option "XkbOptions" "ctrl:nocaps"\n'
        "EndSection\n",
    )


def chroot_disable_xon_xoff() -> None:
    heading("Disabling XON/XOFF flow control")
    append_file("/mnt/etc/profile", "stty -ixon\n")


def chroot_configure_mkinitcpio(cfg: InstallConfig) -> None:
    heading("Configuring mkinitcpio")
    if cfg.lvm.swap_enabled:
        hooks = (
            "HOOKS=(base udev autodetect microcode modconf block "
            "encrypt keyboard keymap consolefont lvm2 resume filesystems fsck)"
        )
    else:
        hooks = (
            "HOOKS=(base udev autodetect microcode modconf block "
            "encrypt keyboard keymap consolefont lvm2 filesystems fsck)"
        )
    run_shell(
        f"sed -i 's/^HOOKS=.*/{hooks}/' /mnt/etc/mkinitcpio.conf"
    )
    run_chroot("mkinitcpio", "-p", cfg.kernel_package)


def chroot_configure_grub(cfg: InstallConfig) -> None:
    heading("Configuring GRUB")
    luks_part = cfg.disk.luks_partition
    grub = cfg.grub
    discard = ":allow-discards" if cfg.disk.trim else ""

    # Get UUIDs and build kernel command line
    if cfg.lvm.swap_enabled:
        run_shell(
            f'LUKS_UUID=$(blkid -s UUID -o value {luks_part}) && '
            f'SWAP_UUID=$(blkid -s UUID -o value /dev/lvmSystem/volSwap) && '
            f'sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT='
            f'\\"cryptdevice=UUID=${{LUKS_UUID}}:lvm-system{discard} '
            f'loglevel=3 quiet resume=UUID=${{SWAP_UUID}} net.ifnames=0\\"/" '
            f'/mnt/etc/default/grub'
        )
    else:
        run_shell(
            f'LUKS_UUID=$(blkid -s UUID -o value {luks_part}) && '
            f'sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT='
            f'\\"cryptdevice=UUID=${{LUKS_UUID}}:lvm-system{discard} '
            f'loglevel=3 quiet net.ifnames=0\\"/" '
            f'/mnt/etc/default/grub'
        )
    append_file("/mnt/etc/default/grub", 'GRUB_ENABLE_CRYPTODISK="y"\n')
    run_shell(
        f"sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=\"{grub.timeout}\"/' "
        f"/mnt/etc/default/grub"
    )
    run_shell(
        'sed -i \'s/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE="menu"/\' '
        '/mnt/etc/default/grub'
    )
    run_shell(
        f"sed -i 's/^GRUB_GFXMODE=.*/GRUB_GFXMODE=\"{grub.gfxmode}\"/' "
        f"/mnt/etc/default/grub"
    )


def chroot_install_grub() -> None:
    heading("Installing GRUB")
    run_chroot("grub-install",
               "--target=x86_64-efi",
               "--efi-directory=/boot/efi",
               "--bootloader-id=artix",
               "--recheck")
    run_chroot("grub-install",
               "--target=x86_64-efi",
               "--efi-directory=/boot/efi",
               "--removable")
    run_chroot("grub-mkconfig", "-o", "/boot/grub/grub.cfg")


def chroot_enable_services(cfg: InstallConfig) -> None:
    heading("Enabling base dinit services")
    base_services = ["lvm2", "NetworkManager", "elogind", "dbus"]
    if cfg.system.ssh != SshPolicy.DISABLE:
        base_services.append("sshd")

    for svc in base_services:
        symlink(f"/etc/dinit.d/{svc}", f"/mnt/etc/dinit.d/boot.d/{svc}")


def chroot_install_optional_services(cfg: InstallConfig) -> None:
    if not cfg.optional_services:
        return
    heading("Installing optional services")

    packages: list[str] = []
    for svc in cfg.optional_services:
        packages.extend(OPTIONAL_SERVICE_PACKAGES[svc])
    if packages:
        run_chroot("pacman", "-S", "--noconfirm", *packages)

    for svc in cfg.optional_services:
        name = OPTIONAL_SERVICE_NAMES[svc]
        symlink(f"/etc/dinit.d/{name}", f"/mnt/etc/dinit.d/boot.d/{name}")


def chroot_install_extra_packages(cfg: InstallConfig) -> None:
    if not cfg.extra_packages:
        return
    heading("Installing extra packages")
    run_chroot("pacman", "-S", "--noconfirm", *cfg.extra_packages)


def chroot_create_user(cfg: InstallConfig) -> None:
    heading(f"Creating user account: {cfg.system.username}")
    run_chroot("useradd", "-m", "-G", "wheel", "-s", "/bin/bash",
               cfg.system.username)
    print(f"Set password for {cfg.system.username}:")
    run_chroot("passwd", cfg.system.username)

    # Enable sudo for wheel group via sed (avoid interactive visudo)
    run_shell(
        "sed -i 's/^# *%wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' "
        "/mnt/etc/sudoers"
    )


def chroot_configure_ssh(cfg: InstallConfig) -> None:
    if cfg.system.ssh == SshPolicy.DISABLE:
        return
    heading("Configuring SSH")
    username = cfg.system.username
    home = f"/mnt/home/{username}"

    # Copy host keys from live ISO so fingerprint survives reboot
    run_shell("cp -p /etc/ssh/ssh_host_* /mnt/etc/ssh/")

    # Install authorized keys
    ssh_dir = f"{home}/.ssh"
    makedirs(ssh_dir, mode=0o700, exist_ok=True)
    authorized_keys = "\n".join(cfg.system.ssh_authorized_keys) + "\n"
    write_file(f"{ssh_dir}/authorized_keys", authorized_keys, mode=0o600)

    # chown to the user (look up uid/gid from /mnt/etc/passwd)
    run_chroot("chown", "-R", f"{username}:{username}",
               f"/home/{username}/.ssh")

    if cfg.system.ssh == SshPolicy.ENABLE_KEYS_ONLY:
        # Disable password authentication
        run_shell(
            "sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication no/' "
            "/mnt/etc/ssh/sshd_config"
        )


def copy_artix_dev(cfg: InstallConfig, config_path: str | None, script_path: str | None) -> None:
    heading("Copying artix-dev to installed system")
    makedirs("/mnt/root/artix-dev", exist_ok=True)
    if script_path and os.path.isfile(script_path):
        run("cp", script_path, "/mnt/root/artix-dev/artix-dev.pyz")
    write_file("/mnt/root/artix-dev/config.toml", cfg.to_toml())
    if config_path and os.path.isfile(config_path):
        run("cp", config_path, "/mnt/root/artix-dev/config.orig.toml")

    write_file("/mnt/etc/motd",
               "\n"
               "  ┌──────────────────────────────────────────────────────┐\n"
               "  │  artix-dev: Phase 1 complete                         │\n"
               "  │                                                      │\n"
               "  │  To finish setup, run:                               │\n"
               "  │    sudo python3 /root/artix-dev/artix-dev.pyz setup  │\n"
               "  │                                                      │\n"
               "  └──────────────────────────────────────────────────────┘\n"
               "\n"
               )


def unmount_and_finish() -> None:
    heading("Unmounting and finishing")
    run("umount", "-R", "/mnt")
    run("swapoff", "-a")
    run("vgchange", "-an", "lvmSystem")
    run("cryptsetup", "luksClose", "lvm-system")
    run("sync")
    print("\nInstallation complete. You may now reboot.")


def run_phase1(cfg: InstallConfig, dry_run: bool = False,
               config_path: str | None = None) -> None:
    """Execute the full Phase 1 installation from the live USB."""
    import artix_dev.run as run_mod
    run_mod.DRY_RUN = dry_run

    if not dry_run and os.geteuid() != 0:
        die("Phase 1 must be run as root")

    errors = cfg.validate_system()
    if errors:
        for err in errors:
            print(f"Config error: {err}")
        die("Fix config errors before running install")

    # Summary and confirmation
    print()
    print(f"  Hostname:   {cfg.system.hostname}")
    print(f"  Disk:       {cfg.disk.device} ({cfg.disk.disk_type.value})")
    print(f"  ESP:        {cfg.disk.esp_partition} ({cfg.disk.esp_size})")
    print(f"  LUKS:       {cfg.disk.luks_partition} ({cfg.luks.cipher})")
    swap_desc = cfg.lvm.swap_size if cfg.lvm.swap_enabled else "disabled"
    print(f"  LVM:        boot={cfg.lvm.boot_size}, swap={swap_desc}, root=remaining")
    print(f"  Kernel:     {cfg.kernel_package}")
    print(f"  Username:   {cfg.system.username}")
    print(f"  Locale:     {cfg.system.locale}")
    print(f"  Timezone:   {cfg.system.timezone}")
    print(f"  SSH:        {cfg.system.ssh.value}")
    if cfg.system.ssh_authorized_keys:
        print(f"  SSH keys:   {len(cfg.system.ssh_authorized_keys)}")
    features = ", ".join(f.value for f in sorted(cfg.features, key=lambda f: f.value))
    print(f"  Features:   {features or 'none'}")
    services = ", ".join(s.value for s in sorted(cfg.optional_services, key=lambda s: s.value))
    print(f"  Services:   {services or 'none'}")
    print()
    print(f"  *** ALL DATA ON {cfg.disk.device} WILL BE DESTROYED ***")
    print()

    if not dry_run:
        while True:
            try:
                answer = input("  Type YES to proceed (or no to cancel): ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                die("Aborted by user")
            if answer == "YES":
                break
            if answer.lower() in ("n", "no", "quit", "exit", "abort"):
                die("Aborted by user")

    install_live_deps()
    partition_disk(cfg)
    setup_luks(cfg)
    setup_lvm(cfg)
    format_partitions(cfg)
    mount_partitions(cfg)
    install_base(cfg)
    copy_wifi_config()
    generate_fstab(cfg)

    # Chroot configuration
    chroot_set_root_password()
    chroot_init_keyring()
    chroot_configure_locale(cfg)
    chroot_configure_timezone(cfg)
    chroot_configure_hostname(cfg)
    chroot_configure_capslock(cfg)
    chroot_disable_xon_xoff()
    chroot_configure_mkinitcpio(cfg)
    chroot_configure_grub(cfg)
    chroot_install_grub()
    chroot_enable_services(cfg)
    chroot_install_optional_services(cfg)
    chroot_install_extra_packages(cfg)
    chroot_create_user(cfg)
    chroot_configure_ssh(cfg)

    # Detect the script path (works for both .pyz and source)
    script_path = sys.argv[0] if sys.argv else None
    copy_artix_dev(cfg, config_path, script_path)

    unmount_and_finish()
