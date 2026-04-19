.PHONY: test lint fmt security install-dev status

test:
	py -3.12 -m pytest tests/ --cov=hooks --cov-fail-under=70 -q

lint:
	py -3.12 -m black --check . && py -3.12 -m flake8 .

fmt:
	py -3.12 -m black .

security:
	py -3.12 -m pip_audit -r requirements-dev.txt -r requirements.txt

install-dev:
	py -3.12 -m pip install -r requirements-dev.txt && py -3.12 -m pre-commit install

status:
	@if [ -f hooks/handlers/on-status.py ]; then py -3.12 hooks/handlers/on-status.py; fi
