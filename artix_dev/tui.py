"""Interactive TUI for building an InstallConfig."""

from __future__ import annotations

import os
import re
import subprocess

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RadioButton,
    RadioSet,
    Rule,
    Static,
)

from artix_dev.config import (
    DiskType,
    Feature,
    InstallConfig,
    Kernel,
    OptionalService,
    SshPolicy,
)

_SIZE_RE = re.compile(r'^\d+(\.\d+)?[KMGTkmgt]$')

TABS = [
    ("welcome", "Welcome"),
    ("disk", "Disk"),
    ("system", "System"),
    ("ssh", "SSH"),
    ("features", "Features"),
    ("extras", "Extras"),
    ("advanced", "Advanced"),
    ("review", "Review"),
]

_NUM_KEY_SLOTS = 5


def _valid_size(value: str) -> bool:
    return bool(_SIZE_RE.match(value.strip()))


def _list_disks() -> list[dict]:
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


class ConfirmDelete(ModalScreen[bool]):
    CSS = """
    ConfirmDelete {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        max-height: 10;
        padding: 1 2;
        background: $surface;
        border: thick $error;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label("Delete saved config and reset all fields?")
            yield Label("")
            with Center():
                with Horizontal():
                    yield Button("Delete", variant="error", id="confirm-yes")
                    yield Button("Cancel", id="confirm-no")

    @on(Button.Pressed, "#confirm-yes")
    def confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def cancel(self) -> None:
        self.dismiss(False)


class ArtixInstaller(App):
    CSS = """
    #layout {
        height: 1fr;
    }
    #sidebar {
        width: 18;
        dock: left;
        background: $surface;
    }
    #sidebar ListView {
        height: auto;
    }
    #content {
        width: 1fr;
    }
    #content > VerticalScroll {
        padding: 0 2;
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
    #main {
        width: 1fr;
    }
    #top-nav {
        dock: top;
        height: auto;
        align-horizontal: right;
    }
    #top-nav Button {
        margin: 0 1;
    }
    #tab-nav-bar {
        height: auto;
    }
    Button {
        margin: 1 1;
    }
    Input {
        margin: 0 0 1 0;
    }
    Checkbox, RadioButton {
        margin: 0 0 0 2;
    }
    #toml-preview {
        margin: 1 0;
        padding: 1 2;
        background: $surface;
    }
    """
    TITLE = "artix-dev installer"

    def __init__(self, cfg: InstallConfig | None = None,
                 config_path: str | None = None) -> None:
        super().__init__()
        self.cfg = cfg or InstallConfig()
        self.config_path = config_path
        self.result: tuple[str, InstallConfig] | None = None
        self.disks = _list_disks()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="layout"):
            with Vertical(id="sidebar"):
                yield ListView(
                    *[ListItem(Label(label), id=f"tab-{key}")
                      for key, label in TABS],
                    id="nav",
                )
            with Vertical(id="main"):
                with Horizontal(id="top-nav"):
                    yield Button("Prev", id="prev")
                    yield Button("Next", variant="primary", id="next")
                with ContentSwitcher(id="content", initial="welcome"):
                    yield from self._welcome_tab()
                    yield from self._disk_tab()
                    yield from self._system_tab()
                    yield from self._ssh_tab()
                    yield from self._features_tab()
                    yield from self._extras_tab()
                    yield from self._advanced_tab()
                    yield from self._review_tab()
        yield Footer()

    def _tab_nav(self) -> ComposeResult:
        """Save and Exit button for each tab."""
        yield Rule()
        with Horizontal(id="tab-nav-bar"):
            yield Button("Save and Exit", id="save")

    # --- Tab content ---

    def _welcome_tab(self) -> ComposeResult:
        with VerticalScroll(id="welcome"):
            yield Label("Welcome to artix-dev", classes="title")
            yield Rule()
            yield Static(
                "[italic]This is an unofficial community installer, not\n"
                "affiliated with the Artix Linux project.[/]\n"
                "\n"
                "artix-dev sets up Artix Linux with full disk encryption\n"
                "(LUKS + LVM), the dinit init system, and optionally a\n"
                "sway Wayland desktop managed by Nix home-manager.\n"
                "\n"
                "Use the tabs on the left to configure each section.\n"
                "You can fill them in any order. Press [bold]Tab[/] to\n"
                "cycle between fields, or use your mouse.\n"
                "\n"
                "When you're ready, go to [bold]Review[/] to see the\n"
                "full configuration, then [bold]Install[/] to begin or\n"
                "[bold]Save Config[/] to save for later.\n"
                "\n"
                "Press [bold]Ctrl+Q[/] at anytime to exit without saving.\n"
            )
            if self.config_path and os.path.exists(self.config_path):
                yield Rule()
                yield Static(
                    f"Loaded saved config: [bold]{self.config_path}[/]"
                )
                yield Button(
                    "Delete Config & Reset",
                    variant="error",
                    id="delete-config",
                )
            yield from self._tab_nav()

    def _disk_tab(self) -> ComposeResult:
        with VerticalScroll(id="disk"):
            yield Label("Select Target Disk", classes="title")
            yield Rule()
            yield Static(
                "[bold red]WARNING: all data on selected device will be deleted[/]"
            )
            if self.disks:
                saved = self.cfg.disk.device
                match = next(
                    (i for i, d in enumerate(self.disks) if d["device"] == saved),
                    0,
                )
                with RadioSet(id="disk-list"):
                    for i, d in enumerate(self.disks):
                        yield RadioButton(
                            f"{d['device']}  {d['size']}  {d['model']}",
                            value=(i == match),
                        )
            else:
                yield Label("No disks detected.")
            yield Checkbox("Enable SSD TRIM", value=self.cfg.disk.trim, id="trim")
            yield Label("ESP (UEFI) size:")
            yield Input(
                value=self.cfg.disk.esp_size,
                placeholder="e.g. 1G, 512M",
                id="esp-size",
            )
            yield Rule()
            yield Label("LVM boot size:")
            yield Input(
                value=self.cfg.lvm.boot_size,
                placeholder="e.g. 1G",
                id="boot-size",
            )
            has_swap = self.cfg.lvm.swap_size != "0"
            yield Checkbox("Enable swap", value=has_swap, id="swap-enable")
            yield Label("LVM swap size:", id="swap-size-label")
            yield Input(
                value=self.cfg.lvm.swap_size if has_swap else "",
                placeholder="e.g. 16G (match RAM for hibernate)",
                disabled=not has_swap,
                id="swap-size",
            )
            yield from self._tab_nav()

    def _advanced_tab(self) -> ComposeResult:
        with VerticalScroll(id="advanced"):
            yield Label("Advanced Encryption Settings", classes="title")
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
            yield from self._tab_nav()

    def _system_tab(self) -> ComposeResult:
        with VerticalScroll(id="system"):
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
            yield from self._tab_nav()

    def _ssh_tab(self) -> ComposeResult:
        with VerticalScroll(id="ssh"):
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
            yield from self._tab_nav()

    def _features_tab(self) -> ComposeResult:
        with VerticalScroll(id="features"):
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
            yield from self._tab_nav()

    def _extras_tab(self) -> ComposeResult:
        with VerticalScroll(id="extras"):
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
            yield from self._tab_nav()

    def _review_tab(self) -> ComposeResult:
        with VerticalScroll(id="review"):
            yield Label("Review Configuration", classes="title")
            yield Rule()
            yield Static("", id="toml-preview")
            yield Static("", id="validation-errors")
            yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Install", variant="primary", id="install")
                    yield Button("Save and Exit", id="save")

    # --- Navigation ---

    @on(ListView.Selected, "#nav")
    def switch_tab(self, event: ListView.Selected) -> None:
        tab_id = event.item.id
        if tab_id:
            key = tab_id.removeprefix("tab-")
            self.query_one("#content", ContentSwitcher).current = key
            if key == "review":
                self._update_review()

    @on(Checkbox.Changed, "#swap-enable")
    def swap_toggled(self, event: Checkbox.Changed) -> None:
        self.query_one("#swap-size", Input).disabled = not event.value

    def _collect_config(self) -> InstallConfig:
        """Read all form values into the config."""
        cfg = self.cfg

        # Disk
        if self.disks:
            disk_set = self.query_one("#disk-list", RadioSet)
            idx = disk_set.pressed_index
            if idx >= 0:
                disk = self.disks[idx]
                cfg.disk.device = disk["device"]
                cfg.disk.disk_type = disk["type"]
        esp = self.query_one("#esp-size", Input).value.strip()
        if esp:
            cfg.disk.esp_size = esp
        cfg.disk.trim = self.query_one("#trim", Checkbox).value

        # Encryption
        cipher = self.query_one("#cipher", Input).value.strip()
        if cipher:
            cfg.luks.cipher = cipher
        try:
            cfg.luks.key_size = int(self.query_one("#key-size", Input).value)
        except ValueError:
            pass
        hash_val = self.query_one("#hash", Input).value.strip()
        if hash_val:
            cfg.luks.hash = hash_val
        try:
            cfg.luks.iter_time = int(self.query_one("#iter-time", Input).value)
        except ValueError:
            pass
        boot = self.query_one("#boot-size", Input).value.strip()
        if boot:
            cfg.lvm.boot_size = boot
        swap_enabled = self.query_one("#swap-enable", Checkbox).value
        if swap_enabled:
            swap = self.query_one("#swap-size", Input).value.strip()
            if swap:
                cfg.lvm.swap_size = swap
        else:
            cfg.lvm.swap_size = "0"

        # System
        hostname = self.query_one("#hostname", Input).value.strip()
        if hostname:
            cfg.system.hostname = hostname
        username = self.query_one("#username", Input).value.strip()
        if username:
            cfg.system.username = username
        locale = self.query_one("#locale", Input).value.strip()
        if locale:
            cfg.system.locale = locale
        timezone = self.query_one("#timezone", Input).value.strip()
        if timezone:
            cfg.system.timezone = timezone
        tmpfs = self.query_one("#tmpfs-size", Input).value.strip()
        if tmpfs:
            cfg.system.tmpfs_size = tmpfs
        cfg.system.caps_lock_remap = self.query_one("#capslock", Checkbox).value
        kernel_set = self.query_one("#kernel", RadioSet)
        if kernel_set.pressed_index >= 0:
            cfg.system.kernel = list(Kernel)[kernel_set.pressed_index]

        # SSH
        policy_set = self.query_one("#ssh-policy", RadioSet)
        if policy_set.pressed_index >= 0:
            cfg.system.ssh = list(SshPolicy)[policy_set.pressed_index]
        keys = []
        for i in range(_NUM_KEY_SLOTS):
            val = self.query_one(f"#ssh-key-{i}", Input).value.strip()
            if val and not val.startswith("#"):
                keys.append(val)
        cfg.system.ssh_authorized_keys = keys

        # Features
        cfg.features = {
            f for f in Feature
            if self.query_one(f"#feat-{f.value}", Checkbox).value
        }
        cfg.optional_services = {
            s for s in OptionalService
            if self.query_one(f"#svc-{s.value}", Checkbox).value
        }

        # Extras
        repo = self.query_one("#repo", Input).value.strip()
        if repo:
            cfg.sway_home.repo = repo
        clone = self.query_one("#clone-path", Input).value.strip()
        if clone:
            cfg.sway_home.clone_path = clone
        try:
            cfg.grub.timeout = int(self.query_one("#grub-timeout", Input).value)
        except ValueError:
            pass
        gfxmode = self.query_one("#grub-gfxmode", Input).value.strip()
        if gfxmode:
            cfg.grub.gfxmode = gfxmode

        return cfg

    def _validate_all(self) -> list[str]:
        """Validate all form fields and return errors."""
        errors: list[str] = []

        # Disk
        if self.disks:
            disk_set = self.query_one("#disk-list", RadioSet)
            if disk_set.pressed_index < 0:
                errors.append("Disk: select a target disk")
        else:
            errors.append("Disk: no disks available")
        esp = self.query_one("#esp-size", Input).value.strip()
        if not _valid_size(esp):
            errors.append("Disk: ESP size must be valid (e.g. 1G)")

        # Encryption
        if not self.query_one("#cipher", Input).value.strip():
            errors.append("Advanced: cipher is required")
        try:
            int(self.query_one("#key-size", Input).value)
        except ValueError:
            errors.append("Advanced: key size must be a number")
        if not self.query_one("#hash", Input).value.strip():
            errors.append("Advanced: hash is required")
        try:
            int(self.query_one("#iter-time", Input).value)
        except ValueError:
            errors.append("Advanced: iteration time must be a number")
        boot = self.query_one("#boot-size", Input).value.strip()
        if not _valid_size(boot):
            errors.append("Disk: boot size must be valid (e.g. 1G)")
        if self.query_one("#swap-enable", Checkbox).value:
            swap = self.query_one("#swap-size", Input).value.strip()
            if not _valid_size(swap):
                errors.append("Disk: swap size must be valid (e.g. 16G)")

        # System
        hostname = self.query_one("#hostname", Input).value.strip()
        if not hostname or not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', hostname):
            errors.append("System: invalid hostname")
        username = self.query_one("#username", Input).value.strip()
        if not username or username == "root" or not re.match(r'^[a-z_][a-z0-9_-]*$', username):
            errors.append("System: invalid username")
        if not self.query_one("#locale", Input).value.strip():
            errors.append("System: locale is required")
        if not self.query_one("#timezone", Input).value.strip():
            errors.append("System: timezone is required")
        tmpfs = self.query_one("#tmpfs-size", Input).value.strip()
        if not _valid_size(tmpfs):
            errors.append("System: tmpfs size must be valid (e.g. 8G)")

        # SSH
        policy_set = self.query_one("#ssh-policy", RadioSet)
        policy_idx = policy_set.pressed_index
        if policy_idx >= 0:
            policy = list(SshPolicy)[policy_idx]
            if policy == SshPolicy.ENABLE_KEYS_ONLY:
                keys = [
                    self.query_one(f"#ssh-key-{i}", Input).value.strip()
                    for i in range(_NUM_KEY_SLOTS)
                    if self.query_one(f"#ssh-key-{i}", Input).value.strip()
                ]
                if not keys:
                    errors.append("SSH: keys-only requires at least one public key")
                valid_prefixes = (
                    "ssh-ed25519 ", "ssh-rsa ", "ssh-dss ",
                    "ecdsa-sha2-", "sk-ssh-ed25519@", "sk-ecdsa-sha2-",
                )
                for key in keys:
                    if not any(key.startswith(p) for p in valid_prefixes):
                        errors.append(f"SSH: invalid key format: {key[:30]}...")
                        break

        # Extras
        try:
            int(self.query_one("#grub-timeout", Input).value)
        except ValueError:
            errors.append("Extras: GRUB timeout must be a number")

        return errors

    def _update_review(self) -> None:
        """Update the review tab with current config and validation."""
        cfg = self._collect_config()
        from rich.text import Text
        self.query_one("#toml-preview", Static).update(Text(cfg.to_toml()))
        errors = self._validate_all()
        if errors:
            text = "[bold red]Validation Errors:[/]\n" + "\n".join(f"  - {e}" for e in errors)
        else:
            text = "[bold green]Configuration is valid.[/]"
        self.query_one("#validation-errors", Static).update(text)

    # --- Actions ---

    @on(Button.Pressed, "#next")
    def do_next(self) -> None:
        switcher = self.query_one("#content", ContentSwitcher)
        current = switcher.current
        tab_keys = [k for k, _ in TABS]
        try:
            idx = tab_keys.index(current)
        except ValueError:
            return
        if idx < len(tab_keys) - 1:
            next_key = tab_keys[idx + 1]
            switcher.current = next_key
            nav = self.query_one("#nav", ListView)
            nav.index = idx + 1
            if next_key == "review":
                self._update_review()

    @on(Button.Pressed, "#prev")
    def do_prev(self) -> None:
        switcher = self.query_one("#content", ContentSwitcher)
        current = switcher.current
        tab_keys = [k for k, _ in TABS]
        try:
            idx = tab_keys.index(current)
        except ValueError:
            return
        if idx > 0:
            prev_key = tab_keys[idx - 1]
            switcher.current = prev_key
            nav = self.query_one("#nav", ListView)
            nav.index = idx - 1
            if prev_key == "review":
                self._update_review()

    @on(Button.Pressed, "#delete-config")
    def do_delete_config(self) -> None:
        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                if self.config_path and os.path.exists(self.config_path):
                    os.remove(self.config_path)
                self.result = ("reset", InstallConfig())
                self.exit()
        self.push_screen(ConfirmDelete(), on_confirm)

    @on(Button.Pressed, "#install")
    def do_install(self) -> None:
        errors = self._validate_all()
        if errors:
            self.notify("Fix validation errors before installing", severity="error")
            return
        self.result = ("install", self._collect_config())
        self.exit()

    @on(Button.Pressed, "#save")
    def do_save(self) -> None:
        self.result = ("save", self._collect_config())
        self.exit()


def run_tui(cfg: InstallConfig | None = None,
            config_path: str | None = None) -> tuple[str, InstallConfig] | None:
    app = ArtixInstaller(cfg, config_path=config_path)
    app.run()
    return app.result
