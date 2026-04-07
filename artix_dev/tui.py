"""Interactive TUI for building an InstallConfig."""

from __future__ import annotations

import os
import re
import subprocess

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Pretty,
    RadioButton,
    RadioSet,
    Rule,
    Static,
    TextArea,
)

from artix_dev.config import (
    DEFAULT_EXTRA_PACKAGES,
    DEFAULT_FLATPAK_APPS,
    DiskType,
    Feature,
    InstallConfig,
    Kernel,
    OptionalService,
    SshPolicy,
    _parse_size,
)

_SIZE_RE = re.compile(r'^\d+(\.\d+)?[KMGTkmgt]$')


def _valid_size(value: str) -> bool:
    """Check if a string is a valid size like '1G', '512M'."""
    return bool(_SIZE_RE.match(value.strip()))


def _list_disks() -> list[dict]:
    """List available block devices."""
    try:
        result = subprocess.run(
            ["lsblk", "-dno", "NAME,SIZE,MODEL,TYPE"],
            capture_output=True, text=True,
        )
        disks = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 2 and parts[-1].strip() == "disk":
                name = parts[0]
                size = parts[1]
                model = parts[2] if len(parts) >= 4 else ""
                disks.append({
                    "device": f"/dev/{name}",
                    "size": size,
                    "model": model,
                    "type": DiskType.NVME if "nvme" in name else DiskType.OTHER,
                })
        return disks
    except FileNotFoundError:
        return []


def _nav_buttons(*buttons: str) -> ComposeResult:
    """Yield centered navigation buttons."""
    with Center():
        with Horizontal():
            if "prev" in buttons:
                yield Button("Previous", id="prev")
            if "next" in buttons:
                yield Button("Next", variant="primary", id="next")
            if "install" in buttons:
                yield Button("Install", variant="primary", id="install")
            if "save" in buttons:
                yield Button("Save Config", id="save")


class DiskScreen(Screen):
    BINDINGS = [Binding("escape", "quit", "Quit")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.disks = _list_disks()

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Select Target Disk", classes="title")
            yield Rule()
            if self.disks:
                with RadioSet(id="disk-list"):
                    for i, d in enumerate(self.disks):
                        yield RadioButton(
                            f"{d['device']}  {d['size']}  {d['model']}",
                            value=(i == 0),
                        )
            else:
                yield Label("No disks detected.")
            yield Label("ESP size:")
            yield Input(
                value=self.cfg.disk.esp_size,
                placeholder="e.g. 1G, 512M",
                id="esp-size",
            )
            yield Checkbox("Enable SSD TRIM", value=self.cfg.disk.trim, id="trim")
            yield Rule()
            yield from _nav_buttons("next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        if not self.disks:
            self.notify("No disks available", severity="error")
            return
        disk_set = self.query_one("#disk-list", RadioSet)
        idx = disk_set.pressed_index
        if idx < 0:
            self.notify("Select a disk from the list", severity="error")
            return
        esp = self.query_one("#esp-size", Input).value.strip()
        if not esp:
            self.notify("ESP size is required", severity="error")
            return
        if not _valid_size(esp):
            self.notify("ESP size must be a valid size (e.g. 1G, 512M)", severity="error")
            return
        disk = self.disks[idx]
        self.cfg.disk.device = disk["device"]
        self.cfg.disk.disk_type = disk["type"]
        self.cfg.disk.esp_size = esp
        self.cfg.disk.trim = self.query_one("#trim", Checkbox).value
        self.app.push_screen(LuksScreen(self.cfg))

    def action_quit(self) -> None:
        self.app.exit()


class LuksScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Encryption Settings", classes="title")
            yield Rule()
            yield Label("LUKS cipher:")
            yield Input(
                value=self.cfg.luks.cipher,
                placeholder="e.g. serpent-xts-plain64, aes-xts-plain64",
                id="cipher",
            )
            yield Label("Key size (bits):")
            yield Input(
                value=str(self.cfg.luks.key_size),
                placeholder="e.g. 256, 512",
                id="key-size",
            )
            yield Label("Hash:")
            yield Input(
                value=self.cfg.luks.hash,
                placeholder="e.g. sha512, sha256",
                id="hash",
            )
            yield Label("Iteration time (ms):")
            yield Input(
                value=str(self.cfg.luks.iter_time),
                placeholder="e.g. 10000",
                id="iter-time",
            )
            yield Rule()
            yield Label("LVM boot size:")
            yield Input(
                value=self.cfg.lvm.boot_size,
                placeholder="e.g. 1G",
                id="boot-size",
            )
            yield Label("LVM swap size:")
            yield Input(
                value=self.cfg.lvm.swap_size,
                placeholder="e.g. 16G (match RAM for hibernate)",
                id="swap-size",
            )
            yield Rule()
            yield from _nav_buttons("prev", "next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        cipher = self.query_one("#cipher", Input).value.strip()
        key_size = self.query_one("#key-size", Input).value.strip()
        hash_val = self.query_one("#hash", Input).value.strip()
        iter_time = self.query_one("#iter-time", Input).value.strip()
        boot = self.query_one("#boot-size", Input).value.strip()
        swap = self.query_one("#swap-size", Input).value.strip()
        if not cipher:
            self.notify("LUKS cipher is required", severity="error")
            return
        if not hash_val:
            self.notify("Hash is required", severity="error")
            return
        try:
            int(key_size)
        except ValueError:
            self.notify("Key size must be a number (bits)", severity="error")
            return
        try:
            int(iter_time)
        except ValueError:
            self.notify("Iteration time must be a number (ms)", severity="error")
            return
        if not _valid_size(boot):
            self.notify("Boot size must be a valid size (e.g. 1G)", severity="error")
            return
        if not _valid_size(swap):
            self.notify("Swap size must be a valid size (e.g. 16G)", severity="error")
            return
        self.cfg.luks.cipher = cipher
        self.cfg.luks.key_size = int(key_size)
        self.cfg.luks.hash = hash_val
        self.cfg.luks.iter_time = int(iter_time)
        self.cfg.lvm.boot_size = boot
        self.cfg.lvm.swap_size = swap
        self.app.push_screen(SystemScreen(self.cfg))

    @on(Button.Pressed, "#prev")
    def prev_screen(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class SystemScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("System Configuration", classes="title")
            yield Rule()
            yield Label("Hostname:")
            yield Input(
                value=self.cfg.system.hostname,
                placeholder="e.g. artix, mybox, thinkpad",
                id="hostname",
            )
            yield Label("Username:")
            yield Input(
                value=self.cfg.system.username,
                placeholder="e.g. user, alice (lowercase, not root)",
                id="username",
            )
            yield Label("Locale:")
            yield Input(
                value=self.cfg.system.locale,
                placeholder="e.g. en_US.UTF-8",
                id="locale",
            )
            yield Label("Timezone:")
            yield Input(
                value=self.cfg.system.timezone,
                placeholder="e.g. US/Mountain, America/New_York, UTC",
                id="timezone",
            )
            yield Label("Tmpfs size (/tmp):")
            yield Input(
                value=self.cfg.system.tmpfs_size,
                placeholder="e.g. 8G (half of RAM is typical)",
                id="tmpfs-size",
            )
            yield Checkbox(
                "Remap Caps Lock to Control",
                value=self.cfg.system.caps_lock_remap,
                id="capslock",
            )
            yield Rule()
            yield Label("Kernel:")
            with RadioSet(id="kernel"):
                for k in Kernel:
                    yield RadioButton(
                        k.value,
                        value=(k == self.cfg.system.kernel),
                    )
            yield Rule()
            yield from _nav_buttons("prev", "next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        hostname = self.query_one("#hostname", Input).value.strip()
        username = self.query_one("#username", Input).value.strip()
        locale = self.query_one("#locale", Input).value.strip()
        timezone = self.query_one("#timezone", Input).value.strip()
        tmpfs = self.query_one("#tmpfs-size", Input).value.strip()
        if not hostname:
            self.notify("Hostname is required", severity="error")
            return
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', hostname):
            self.notify("Invalid hostname (letters, digits, hyphens only)", severity="error")
            return
        if not username:
            self.notify("Username is required", severity="error")
            return
        if username == "root":
            self.notify("Username must not be root", severity="error")
            return
        if not re.match(r'^[a-z_][a-z0-9_-]*$', username):
            self.notify("Invalid username (lowercase, start with letter/underscore)", severity="error")
            return
        if not locale:
            self.notify("Locale is required", severity="error")
            return
        if not timezone:
            self.notify("Timezone is required", severity="error")
            return
        if not _valid_size(tmpfs):
            self.notify("Tmpfs size must be a valid size (e.g. 8G)", severity="error")
            return
        self.cfg.system.hostname = hostname
        self.cfg.system.username = username
        self.cfg.system.locale = locale
        self.cfg.system.timezone = timezone
        self.cfg.system.tmpfs_size = tmpfs
        self.cfg.system.caps_lock_remap = self.query_one("#capslock", Checkbox).value
        kernel_set = self.query_one("#kernel", RadioSet)
        if kernel_set.pressed_index >= 0:
            self.cfg.system.kernel = list(Kernel)[kernel_set.pressed_index]
        self.app.push_screen(SshScreen(self.cfg))

    @on(Button.Pressed, "#prev")
    def prev_screen(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


_NUM_KEY_SLOTS = 5


class SshScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("SSH Configuration", classes="title")
            yield Rule()
            yield Label("SSH policy:")
            with RadioSet(id="ssh-policy"):
                for p in SshPolicy:
                    labels = {
                        "keys_only": "Keys only (disable password auth)",
                        "password": "Password auth enabled",
                        "disable": "Disable SSH entirely",
                    }
                    yield RadioButton(
                        labels[p.value],
                        value=(p == self.cfg.system.ssh),
                    )
            yield Rule()
            yield Label("Authorized public keys:")
            for i in range(_NUM_KEY_SLOTS):
                value = (self.cfg.system.ssh_authorized_keys[i]
                         if i < len(self.cfg.system.ssh_authorized_keys) else "")
                yield Input(
                    value=value,
                    placeholder="ssh-ed25519 AAAA... user@host",
                    id=f"ssh-key-{i}",
                )
            yield Rule()
            yield from _nav_buttons("prev", "next")
        yield Footer()

    def _collect_keys(self) -> list[str]:
        keys = []
        for i in range(_NUM_KEY_SLOTS):
            val = self.query_one(f"#ssh-key-{i}", Input).value.strip()
            if val and not val.startswith("#"):
                keys.append(val)
        return keys

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        policy_set = self.query_one("#ssh-policy", RadioSet)
        if policy_set.pressed_index >= 0:
            self.cfg.system.ssh = list(SshPolicy)[policy_set.pressed_index]
        self.cfg.system.ssh_authorized_keys = self._collect_keys()
        if self.cfg.system.ssh == SshPolicy.ENABLE_KEYS_ONLY:
            if not self.cfg.system.ssh_authorized_keys:
                self.notify("Keys-only SSH requires at least one public key", severity="error")
                return
            valid_prefixes = (
                "ssh-ed25519 ", "ssh-rsa ", "ssh-dss ",
                "ecdsa-sha2-", "sk-ssh-ed25519@", "sk-ecdsa-sha2-",
            )
            for key in self.cfg.system.ssh_authorized_keys:
                if not any(key.startswith(p) for p in valid_prefixes):
                    self.notify(f"Invalid SSH key: {key[:40]}...", severity="error")
                    return
        self.app.push_screen(FeaturesScreen(self.cfg))

    @on(Button.Pressed, "#prev")
    def prev_screen(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class FeaturesScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Features", classes="title")
            yield Rule()
            for f in Feature:
                labels = {
                    "podman": "Rootless Podman containers",
                    "libvirt": "QEMU/libvirt virtual machines",
                    "nix": "Nix package manager",
                    "desktop": "Sway desktop + audio + greetd",
                    "sway_home": "sway-home dotfiles (implies Nix + Desktop)",
                    "flatpak": "Flatpak + Flathub",
                }
                yield Checkbox(
                    labels[f.value],
                    value=(f in self.cfg.features),
                    id=f"feat-{f.value}",
                )
            yield Rule()
            yield Label("Optional Services")
            yield Rule()
            for s in OptionalService:
                yield Checkbox(
                    s.value,
                    value=(s in self.cfg.optional_services),
                    id=f"svc-{s.value}",
                )
            yield Rule()
            yield from _nav_buttons("prev", "next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        self.cfg.features = {
            f for f in Feature
            if self.query_one(f"#feat-{f.value}", Checkbox).value
        }
        self.cfg.optional_services = {
            s for s in OptionalService
            if self.query_one(f"#svc-{s.value}", Checkbox).value
        }
        self.app.push_screen(SwayHomeScreen(self.cfg))

    @on(Button.Pressed, "#prev")
    def prev_screen(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class SwayHomeScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("sway-home & GRUB Settings", classes="title")
            yield Rule()
            yield Label("sway-home git repo:")
            yield Input(
                value=self.cfg.sway_home.repo,
                placeholder="e.g. https://github.com/user/sway-home",
                id="repo",
            )
            yield Label("Clone path:")
            yield Input(
                value=self.cfg.sway_home.clone_path,
                placeholder="e.g. ~/git/vendor/enigmacurry/sway-home",
                id="clone-path",
            )
            yield Rule()
            yield Label("GRUB timeout (seconds):")
            yield Input(
                value=str(self.cfg.grub.timeout),
                placeholder="e.g. 15",
                id="grub-timeout",
            )
            yield Label("GRUB graphics mode:")
            yield Input(
                value=self.cfg.grub.gfxmode,
                placeholder="e.g. auto, 1920x1080",
                id="grub-gfxmode",
            )
            yield Rule()
            yield from _nav_buttons("prev", "next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        timeout = self.query_one("#grub-timeout", Input).value.strip()
        gfxmode = self.query_one("#grub-gfxmode", Input).value.strip()
        repo = self.query_one("#repo", Input).value.strip()
        clone_path = self.query_one("#clone-path", Input).value.strip()
        try:
            self.cfg.grub.timeout = int(timeout)
        except ValueError:
            self.notify("GRUB timeout must be a number", severity="error")
            return
        if not gfxmode:
            self.notify("GRUB graphics mode is required", severity="error")
            return
        if not repo:
            self.notify("sway-home repo is required", severity="error")
            return
        if not clone_path:
            self.notify("Clone path is required", severity="error")
            return
        self.cfg.sway_home.repo = repo
        self.cfg.sway_home.clone_path = clone_path
        self.cfg.grub.gfxmode = gfxmode
        self.app.push_screen(ReviewScreen(self.cfg))

    @on(Button.Pressed, "#prev")
    def prev_screen(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class ReviewScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Review Configuration", classes="title")
            yield Rule()
            yield Static(self.cfg.to_toml(), id="toml-preview")
            yield Rule()
            errors = self.cfg.validate()
            if errors:
                yield Label("Validation Errors:", classes="error-title")
                for err in errors:
                    yield Label(f"  - {err}", classes="error")
                yield Rule()
            yield from _nav_buttons("prev", "install", "save")
        yield Footer()

    @on(Button.Pressed, "#install")
    def do_install(self) -> None:
        errors = self.cfg.validate()
        if errors:
            self.notify("Fix validation errors before installing", severity="error")
            return
        self.app.result = ("install", self.cfg)
        self.app.exit()

    @on(Button.Pressed, "#save")
    def do_save(self) -> None:
        self.app.result = ("save", self.cfg)
        self.app.exit()

    @on(Button.Pressed, "#prev")
    def prev_screen(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class ArtixInstaller(App):
    CSS = """
    Screen {
        align: center top;
    }
    VerticalScroll {
        max-width: 80;
        width: 100%;
    }
    .title {
        text-style: bold;
        color: $accent;
        margin: 1 0;
    }
    .error-title {
        text-style: bold;
        color: $error;
    }
    .error {
        color: $error;
    }
    .help {
        color: $text-muted;
        margin: 0 0 1 0;
    }
    Button {
        margin: 1 1;
    }
    Input, TextArea {
        margin: 0 0 1 0;
    }
    Checkbox, RadioButton {
        margin: 0 0 0 2;
    }
    #toml-preview {
        margin: 1 2;
        padding: 1 2;
        background: $surface;
    }
    """
    TITLE = "artix-dev installer"
    BINDINGS = [Binding("q", "quit", "Quit")]

    def __init__(self, cfg: InstallConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or InstallConfig()
        self.result: tuple[str, InstallConfig] | None = None

    def on_mount(self) -> None:
        self.push_screen(DiskScreen(self.cfg))


def run_tui(cfg: InstallConfig | None = None) -> tuple[str, InstallConfig] | None:
    """Run the TUI and return (action, config) or None if quit."""
    app = ArtixInstaller(cfg)
    app.run()
    return app.result
