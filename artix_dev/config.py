"""Configuration dataclass for Artix Linux installation with TOML serialization."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DiskType(Enum):
    NVME = "nvme"  # partition suffix: p1, p2
    OTHER = "other"  # partition suffix: 1, 2 (virtio, SATA)


class Feature(Enum):
    PODMAN = "podman"
    LIBVIRT = "libvirt"
    NIX = "nix"
    DESKTOP = "desktop"  # sway + audio + greetd
    SWAY_HOME = "sway_home"  # implies NIX and DESKTOP
    FLATPAK = "flatpak"


class OptionalService(Enum):
    NTPD = "ntpd"
    SYSLOG = "syslog-ng"
    ACPID = "acpid"
    CRONIE = "cronie"


class Kernel(Enum):
    HARDENED = "linux-hardened"
    STANDARD = "linux"
    LTS = "linux-lts"
    ZEN = "linux-zen"


@dataclass
class DiskConfig:
    device: str = "/dev/nvme0n1"
    disk_type: DiskType = DiskType.NVME

    @property
    def part_prefix(self) -> str:
        if self.disk_type == DiskType.NVME:
            return f"{self.device}p"
        return self.device

    @property
    def esp_partition(self) -> str:
        return f"{self.part_prefix}1"

    @property
    def luks_partition(self) -> str:
        return f"{self.part_prefix}2"


@dataclass
class LuksConfig:
    cipher: str = "serpent-xts-plain64"
    key_size: int = 512
    hash: str = "sha512"
    iter_time: int = 10000
    luks_type: str = "luks1"  # luks1 required for GRUB encrypted /boot


@dataclass
class LvmConfig:
    boot_size: str = "1G"
    swap_size: str = "16G"
    # root gets the remaining space automatically


@dataclass
class SystemConfig:
    hostname: str = "artix"
    locale: str = "en_US.UTF-8"
    timezone: str = "US/Mountain"
    username: str = "user"
    kernel: Kernel = Kernel.HARDENED
    caps_lock_remap: bool = True
    tmpfs_size: str = "8G"


@dataclass
class SwayHomeConfig:
    repo: str = "https://github.com/EnigmaCurry/sway-home"
    clone_path: str = "~/git/vendor/enigmacurry/sway-home"


@dataclass
class InstallConfig:
    disk: DiskConfig = field(default_factory=DiskConfig)
    luks: LuksConfig = field(default_factory=LuksConfig)
    lvm: LvmConfig = field(default_factory=LvmConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    sway_home: SwayHomeConfig = field(default_factory=SwayHomeConfig)
    features: set[Feature] = field(default_factory=lambda: {
        Feature.PODMAN,
        Feature.NIX,
        Feature.DESKTOP,
        Feature.SWAY_HOME,
        Feature.FLATPAK,
    })
    optional_services: set[OptionalService] = field(default_factory=lambda: {
        OptionalService.NTPD,
        OptionalService.SYSLOG,
        OptionalService.ACPID,
        OptionalService.CRONIE,
    })

    @property
    def kernel_package(self) -> str:
        return self.system.kernel.value

    @property
    def kernel_headers_package(self) -> str:
        return f"{self.system.kernel.value}-headers"

    @property
    def install_podman(self) -> bool:
        return Feature.PODMAN in self.features

    @property
    def install_libvirt(self) -> bool:
        return Feature.LIBVIRT in self.features

    @property
    def install_nix(self) -> bool:
        return Feature.NIX in self.features or Feature.SWAY_HOME in self.features

    @property
    def install_desktop(self) -> bool:
        return Feature.DESKTOP in self.features or Feature.SWAY_HOME in self.features

    @property
    def install_sway_home(self) -> bool:
        return Feature.SWAY_HOME in self.features

    @property
    def install_flatpak(self) -> bool:
        return Feature.FLATPAK in self.features

    def to_toml(self) -> str:
        lines: list[str] = []

        lines.append("[disk]")
        lines.append(f'device = "{self.disk.device}"')
        lines.append(f'type = "{self.disk.disk_type.value}"')

        lines.append("\n[luks]")
        lines.append(f'cipher = "{self.luks.cipher}"')
        lines.append(f"key_size = {self.luks.key_size}")
        lines.append(f'hash = "{self.luks.hash}"')
        lines.append(f"iter_time = {self.luks.iter_time}")
        lines.append(f'luks_type = "{self.luks.luks_type}"')

        lines.append("\n[lvm]")
        lines.append(f'boot_size = "{self.lvm.boot_size}"')
        lines.append(f'swap_size = "{self.lvm.swap_size}"')

        lines.append("\n[system]")
        lines.append(f'hostname = "{self.system.hostname}"')
        lines.append(f'locale = "{self.system.locale}"')
        lines.append(f'timezone = "{self.system.timezone}"')
        lines.append(f'username = "{self.system.username}"')
        lines.append(f'kernel = "{self.system.kernel.value}"')
        lines.append(f"caps_lock_remap = {str(self.system.caps_lock_remap).lower()}")
        lines.append(f'tmpfs_size = "{self.system.tmpfs_size}"')

        lines.append("\n[sway_home]")
        lines.append(f'repo = "{self.sway_home.repo}"')
        lines.append(f'clone_path = "{self.sway_home.clone_path}"')

        lines.append("\n[features]")
        lines.append(f"enable = [{', '.join(f'\"{f.value}\"' for f in sorted(self.features, key=lambda f: f.value))}]")

        lines.append("\n[services]")
        lines.append(f"enable = [{', '.join(f'\"{s.value}\"' for s in sorted(self.optional_services, key=lambda s: s.value))}]")

        return "\n".join(lines) + "\n"

    @classmethod
    def from_toml(cls, text: str) -> InstallConfig:
        data = tomllib.loads(text)

        disk = DiskConfig(
            device=data.get("disk", {}).get("device", DiskConfig.device),
            disk_type=DiskType(data.get("disk", {}).get("type", DiskType.NVME.value)),
        )

        luks_data = data.get("luks", {})
        luks = LuksConfig(
            cipher=luks_data.get("cipher", LuksConfig.cipher),
            key_size=luks_data.get("key_size", LuksConfig.key_size),
            hash=luks_data.get("hash", LuksConfig.hash),
            iter_time=luks_data.get("iter_time", LuksConfig.iter_time),
            luks_type=luks_data.get("luks_type", LuksConfig.luks_type),
        )

        lvm_data = data.get("lvm", {})
        lvm = LvmConfig(
            boot_size=lvm_data.get("boot_size", LvmConfig.boot_size),
            swap_size=lvm_data.get("swap_size", LvmConfig.swap_size),
        )

        sys_data = data.get("system", {})
        system = SystemConfig(
            hostname=sys_data.get("hostname", SystemConfig.hostname),
            locale=sys_data.get("locale", SystemConfig.locale),
            timezone=sys_data.get("timezone", SystemConfig.timezone),
            username=sys_data.get("username", SystemConfig.username),
            kernel=Kernel(sys_data.get("kernel", Kernel.HARDENED.value)),
            caps_lock_remap=sys_data.get("caps_lock_remap", SystemConfig.caps_lock_remap),
            tmpfs_size=sys_data.get("tmpfs_size", SystemConfig.tmpfs_size),
        )

        sh_data = data.get("sway_home", {})
        sway_home = SwayHomeConfig(
            repo=sh_data.get("repo", SwayHomeConfig.repo),
            clone_path=sh_data.get("clone_path", SwayHomeConfig.clone_path),
        )

        feat_data = data.get("features", {})
        svc_data = data.get("services", {})

        if "enable" in feat_data:
            features = {Feature(f) for f in feat_data["enable"]}
        else:
            features = None  # use dataclass default

        if "enable" in svc_data:
            services = {OptionalService(s) for s in svc_data["enable"]}
        else:
            services = None  # use dataclass default

        kwargs: dict = dict(
            disk=disk, luks=luks, lvm=lvm, system=system, sway_home=sway_home,
        )
        if features is not None:
            kwargs["features"] = features
        if services is not None:
            kwargs["optional_services"] = services

        return cls(**kwargs)

    @classmethod
    def load(cls, path: Path) -> InstallConfig:
        return cls.from_toml(path.read_text())

    def save(self, path: Path) -> None:
        path.write_text(self.to_toml())
