# List available recipes
default:
    @just --list

# Run tests
test:
    uv run pytest tests/ -v
