.PHONY: test lint fmt security install-dev install-statusline install status docs sync-cache validate-analysts setup ci-gate workflows analytics adapters

ifeq ($(OS),Windows_NT)
	PYTHON := py -3.12
else
	PYTHON := python3
endif

test:
	$(PYTHON) -m pytest tests/ --cov=hooks/lib --cov=packs/domains/domain_lib --cov-fail-under=70 -q

lint:
	$(PYTHON) -m black --check . && $(PYTHON) -m flake8 .

fmt:
	$(PYTHON) -m black .

security:
	$(PYTHON) -m pip_audit -r requirements-dev.txt -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt && $(PYTHON) -m pre-commit install

install-statusline:
	@cp scripts/statusline-command.sh "$$HOME/.claude/statusline-command.sh"
	@echo "Copied statusline-command.sh to ~/.claude/"
	@echo "Add to ~/.claude/settings.json:"
	@echo '  "statusLine": { "type": "command", "command": "bash \"~/.claude/statusline-command.sh\"" }'

status:
	@if [ -f hooks/handlers/on-status.py ]; then $(PYTHON) hooks/handlers/on-status.py; fi

docs:
	$(PYTHON) scripts/sync_docs.py

sync-cache:
	powershell.exe -ExecutionPolicy Bypass -File scripts/sync-cache.ps1

validate-analysts:
	$(PYTHON) scripts/validate_analysts.py

setup:
	$(PYTHON) scripts/setup.py

ci-gate:
	$(PYTHON) scripts/ci_gate.py

install:
	$(PYTHON) scripts/generate_routing.py

workflows:
	$(PYTHON) hooks/lib/workflow_registry.py

analytics:
	$(PYTHON) scripts/ds_analytics/main.py $(if $(PROJECT),--project $(PROJECT),)

adapters:
	$(PYTHON) scripts/build_adapters.py $(if $(PLATFORM),--platform $(PLATFORM),)
