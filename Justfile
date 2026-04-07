# List available recipes
help:
    @just --list

# Run tests
test:
    uv run pytest tests/ -v

# Build artix-dev.pyz standalone executable
build repo='':
    rm -rf build
    mkdir -p build/app
    cp -r artix_dev build/app/
    # Stamp version with git SHA and repo URL
    printf 'VERSION = "%s"\nREPO = "%s"\nBUILD_TIME = "%s"\n' "$(git rev-parse --short HEAD)" "{{repo}}" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > build/app/artix_dev/_version.py
    # Install runtime deps (if any) into the bundle
    uv export --no-dev --no-emit-project -o build/requirements.txt 2>/dev/null && \
        uv pip install --target build/app -r build/requirements.txt 2>/dev/null || true
    find build/app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    python3 -m zipapp build/app -o artix-dev.pyz -p "/usr/bin/env python3" -m "artix_dev.__main__:main"
    @echo "Built artix-dev.pyz ($(wc -c < artix-dev.pyz) bytes)"

# Run artix-dev with arguments
run *args:
    uv run python -m artix_dev {{args}}

# Dry-run install to show what would be executed
dry-run config='examples/nvme-fde.toml':
    uv run python -m artix_dev install --dry-run {{config}}

# Print default config to stdout
dump-config:
    uv run python -m artix_dev dump-config
