# List available recipes
help:
    @just --list

# Run tests
test:
    uv run pytest tests/ -v

# Render standalone bash install script from config
render config:
    uv run python -m artix_dev render {{config}}

# Print default config to stdout
dump-config:
    uv run python -m artix_dev dump-config
