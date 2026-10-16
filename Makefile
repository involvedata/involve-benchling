.PHONY: install lint type test test-all cov

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests
	ruff format --check src tests

type:
	mypy

test:
	pytest

test-all:
	pytest -m ""

cov:
	pytest --cov --cov-report=term-missing
