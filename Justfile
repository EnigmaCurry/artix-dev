# List available recipes
help:
    @just --list

# Run tests
test:
    uv run pytest tests/ -v
