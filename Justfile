_venv := ".venv"

# Create virtualenv and install test dependencies
setup:
    python3 -m venv {{_venv}}
    {{_venv}}/bin/pip install -q pytest

# Run tests
test: setup
    PYTHONPATH=. {{_venv}}/bin/python3 -m pytest tests/ -v
