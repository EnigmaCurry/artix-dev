# List available recipes
help:
    @just --list

# Run tests
test:
    uv run pytest tests/ -v

# Build artix-dev.pyz standalone executable
build:
    rm -rf build
    mkdir -p build/app
    cp -r artix_dev build/app/
    # Stamp version with git SHA
    printf 'VERSION = "%s"\nREPO = "https://github.com/EnigmaCurry/artix-dev"\n' "$(git rev-parse --short HEAD)" > build/app/artix_dev/_version.py
    # Install runtime deps (if any) into the bundle
    uv export --no-dev --no-emit-project -o build/requirements.txt 2>/dev/null && \
        uv pip install --target build/app -r build/requirements.txt 2>/dev/null || true
    find build/app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    python3 -m zipapp build/app -o artix-dev.pyz -p "/usr/bin/env python3" -m "artix_dev.__main__:main"
    @echo "Built artix-dev.pyz ($(wc -c < artix-dev.pyz) bytes)"

# Dry-run install to show what would be executed
dry-run config='examples/nvme-fde.toml':
    uv run python -m artix_dev install --dry-run {{config}}

# Print default config to stdout
dump-config:
    uv run python -m artix_dev dump-config
