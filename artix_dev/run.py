"""Shell command execution helpers."""

from __future__ import annotations

import subprocess
import sys

DRY_RUN = False


def run(*args: str) -> None:
    """Run a command, printing it first. Raises on failure."""
    print(f">>> {' '.join(args)}", flush=True)
    if not DRY_RUN:
        subprocess.run(args, check=True)


def run_chroot(*args: str) -> None:
    """Run a command inside artix-chroot /mnt."""
    cmd = ["artix-chroot", "/mnt", *args]
    print(f">>> {' '.join(cmd)}", flush=True)
    if not DRY_RUN:
        subprocess.run(cmd, check=True)


def run_shell(script: str, chroot: bool = False) -> None:
    """Run a shell script string. Use for pipelines or redirects."""
    if chroot:
        cmd = ["artix-chroot", "/mnt", "/bin/bash", "-c", script]
    else:
        cmd = ["/bin/bash", "-c", script]
    print(f">>> {script}", flush=True)
    if not DRY_RUN:
        subprocess.run(cmd, check=True)


def write_file(path: str, content: str, *, mode: int | None = None) -> None:
    """Write content to a file on the host filesystem."""
    print(f">>> write {path}", flush=True)
    if not DRY_RUN:
        with open(path, "w") as f:
            f.write(content)
        if mode is not None:
            import os
            os.chmod(path, mode)


def append_file(path: str, content: str) -> None:
    """Append content to a file on the host filesystem."""
    print(f">>> append {path}", flush=True)
    if not DRY_RUN:
        with open(path, "a") as f:
            f.write(content)


def makedirs(path: str, **kwargs) -> None:
    """Create directories, respecting DRY_RUN."""
    print(f">>> mkdir -p {path}", flush=True)
    if not DRY_RUN:
        import os
        os.makedirs(path, **kwargs)


def symlink(src: str, dst: str) -> None:
    """Create a symlink, respecting DRY_RUN."""
    print(f">>> ln -s {src} {dst}", flush=True)
    if not DRY_RUN:
        import os
        os.symlink(src, dst)


def run_as_user(username: str, *args: str) -> None:
    """Run a command as a specific user via su."""
    cmd = ["su", "-l", username, "-c", " ".join(args)]
    print(f">>> [{username}] {' '.join(args)}", flush=True)
    if not DRY_RUN:
        subprocess.run(cmd, check=True)


def run_output(*args: str) -> str:
    """Run a command and return its stdout. Not affected by DRY_RUN."""
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout.strip()


def heading(msg: str) -> None:
    """Print a section heading."""
    print(f"\n{'=' * 60}", flush=True)
    print(f"  {msg}", flush=True)
    print(f"{'=' * 60}\n", flush=True)


def die(msg: str) -> None:
    """Print error and exit."""
    print(f"FATAL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)
