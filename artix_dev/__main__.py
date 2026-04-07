"""CLI entry point for artix-dev."""

from __future__ import annotations

import sys
from pathlib import Path

from artix_dev.config import InstallConfig


def usage() -> None:
    print("Usage: artix-dev <command> [config.toml]")
    print()
    print("Commands:")
    print("  install <config.toml>   Run Phase 1 installation from live USB")
    print("  dump-config             Print default config to stdout")
    sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        usage()

    command = args[0]

    if command == "dump-config":
        print(InstallConfig().to_toml())

    elif command == "install":
        if len(args) < 2:
            print("Error: install requires a config file path", file=sys.stderr)
            usage()
        config_path = Path(args[1])
        if not config_path.exists():
            print(f"Error: {config_path} not found", file=sys.stderr)
            sys.exit(1)

        cfg = InstallConfig.load(config_path)
        from artix_dev.phase1 import run_phase1
        run_phase1(cfg)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        usage()


if __name__ == "__main__":
    main()
