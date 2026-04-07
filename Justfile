# List available recipes
help:
    @just --list

# Run tests
test:
    uv run pytest tests/ -v

# Print default config to stdout
dump-config:
    uv run python -m artix_dev dump-config
