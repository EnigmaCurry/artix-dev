"""Tests for config serialization roundtrip."""

from artix_dev.config import (
    DiskType,
    Feature,
    GrubConfig,
    InstallConfig,
    Kernel,
    OptionalService,
    SshPolicy,
)


def test_default_roundtrip():
    original = InstallConfig()
    toml_text = original.to_toml()
    restored = InstallConfig.from_toml(toml_text)

    assert restored.disk.device == original.disk.device
    assert restored.disk.disk_type == original.disk.disk_type
    assert restored.disk.esp_size == original.disk.esp_size
    assert restored.disk.trim == original.disk.trim
    assert restored.luks.cipher == original.luks.cipher
    assert restored.luks.key_size == original.luks.key_size
    assert restored.lvm.swap_size == original.lvm.swap_size
    assert restored.grub.timeout == original.grub.timeout
    assert restored.grub.gfxmode == original.grub.gfxmode
    assert restored.system.hostname == original.system.hostname
    assert restored.system.kernel == original.system.kernel
    assert restored.system.ssh == original.system.ssh
    assert restored.sway_home.repo == original.sway_home.repo
    assert restored.features == original.features
    assert restored.optional_services == original.optional_services
    assert restored.extra_packages == original.extra_packages
    assert restored.flatpak_apps == original.flatpak_apps


def test_custom_values_roundtrip():
    config = InstallConfig()
    config.disk.device = "/dev/vda"
    config.disk.disk_type = DiskType.OTHER
    config.disk.esp_size = "512M"
    config.disk.trim = False
    config.grub.timeout = 5
    config.system.hostname = "mybox"
    config.system.username = "alice"
    config.system.kernel = Kernel.ZEN
    config.system.ssh = SshPolicy.DISABLE
    config.sway_home.repo = "https://github.com/alice/sway-home"
    config.features = {Feature.NIX, Feature.PODMAN}
    config.optional_services = {OptionalService.NTPD}
    config.extra_packages = ["htop", "strace"]
    config.flatpak_apps = ["org.example.App"]

    restored = InstallConfig.from_toml(config.to_toml())

    assert restored.disk.device == "/dev/vda"
    assert restored.disk.disk_type == DiskType.OTHER
    assert restored.disk.part_prefix == "/dev/vda"
    assert restored.disk.esp_size == "512M"
    assert restored.disk.trim is False
    assert restored.grub.timeout == 5
    assert restored.system.hostname == "mybox"
    assert restored.system.kernel == Kernel.ZEN
    assert restored.system.ssh == SshPolicy.DISABLE
    assert restored.kernel_package == "linux-zen"
    assert restored.kernel_headers_package == "linux-zen-headers"
    assert restored.sway_home.repo == "https://github.com/alice/sway-home"
    assert restored.features == {Feature.NIX, Feature.PODMAN}
    assert restored.install_nix is True
    assert restored.install_desktop is False
    assert restored.install_sway_home is False
    assert restored.extra_packages == ["htop", "strace"]
    assert restored.flatpak_apps == ["org.example.App"]


def test_partition_paths_nvme():
    config = InstallConfig()
    assert config.disk.esp_partition == "/dev/nvme0n1p1"
    assert config.disk.luks_partition == "/dev/nvme0n1p2"


def test_partition_paths_virtio():
    config = InstallConfig()
    config.disk.device = "/dev/vda"
    config.disk.disk_type = DiskType.OTHER
    assert config.disk.esp_partition == "/dev/vda1"
    assert config.disk.luks_partition == "/dev/vda2"


def test_feature_implications():
    config = InstallConfig()
    config.features = {Feature.SWAY_HOME}
    assert config.install_sway_home is True
    assert config.install_nix is True
    assert config.install_desktop is True
    assert config.install_podman is False


def test_empty_features_from_toml():
    toml = '[features]\nenable = []\n'
    config = InstallConfig.from_toml(toml)
    assert config.features == set()


def test_ssh_policy_roundtrip():
    for policy in SshPolicy:
        config = InstallConfig()
        config.system.ssh = policy
        restored = InstallConfig.from_toml(config.to_toml())
        assert restored.system.ssh == policy


def test_trim_disabled():
    config = InstallConfig()
    config.disk.trim = False
    toml_text = config.to_toml()
    assert "trim = false" in toml_text
    restored = InstallConfig.from_toml(toml_text)
    assert restored.disk.trim is False


def test_toml_output_readable():
    config = InstallConfig()
    toml_text = config.to_toml()
    assert "[disk]" in toml_text
    assert "[luks]" in toml_text
    assert "[grub]" in toml_text
    assert "[system]" in toml_text
    assert "[sway_home]" in toml_text
    assert "[features]" in toml_text
    assert "[services]" in toml_text
    assert "[packages]" in toml_text
    assert "[flatpak]" in toml_text
    assert 'kernel = "linux-hardened"' in toml_text
    assert 'ssh = "keys_only"' in toml_text
    assert "ssh_authorized_keys" in toml_text


def test_ssh_authorized_keys_roundtrip():
    config = InstallConfig()
    config.system.ssh_authorized_keys = [
        "ssh-ed25519 AAAA... user@host",
        "ssh-rsa BBBB... other@host",
    ]
    restored = InstallConfig.from_toml(config.to_toml())
    assert restored.system.ssh_authorized_keys == [
        "ssh-ed25519 AAAA... user@host",
        "ssh-rsa BBBB... other@host",
    ]


def test_validate_keys_only_requires_keys():
    config = InstallConfig()
    config.system.ssh = SshPolicy.ENABLE_KEYS_ONLY
    config.system.ssh_authorized_keys = []
    errors = config.validate()
    assert len(errors) == 1
    assert "ssh_authorized_keys" in errors[0]


def test_validate_keys_only_with_keys():
    config = InstallConfig()
    config.system.ssh = SshPolicy.ENABLE_KEYS_ONLY
    config.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... user@host"]
    assert config.validate() == []


def test_validate_password_no_keys_ok():
    config = InstallConfig()
    config.system.ssh = SshPolicy.ENABLE_PASSWORD
    config.system.ssh_authorized_keys = []
    assert config.validate() == []


def test_validate_disable_no_keys_ok():
    config = InstallConfig()
    config.system.ssh = SshPolicy.DISABLE
    config.system.ssh_authorized_keys = []
    assert config.validate() == []
