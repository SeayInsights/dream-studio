.PHONY: test lint fmt security install-dev install-statusline install docs sync-cache sync-plugin-cache validate-analysts setup setup-check ci-gate analytics dashboard dashboard-check adapters runtime-check docker-runtime-check

ifeq ($(OS),Windows_NT)
	PYTHON := py -3.12
else
	PYTHON := python3
endif

test:
	$(PYTHON) -m pytest tests/ --cov=hooks/lib --cov=packs/domains/domain_lib --cov-fail-under=70 -q

lint:
	$(PYTHON) -m black --check . && $(PYTHON) interfaces/cli/lint_baseline.py check

fmt:
	$(PYTHON) -m black .

security:
	$(PYTHON) -m pip_audit -r requirements-dev.txt -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt && $(PYTHON) -m pre-commit install

install-statusline:
	@cp interfaces/cli/statusline-command.sh "$$HOME/.claude/statusline-command.sh"
	@echo "Copied statusline-command.sh to ~/.claude/"
	@echo "Add to ~/.claude/settings.json:"
	@echo '  "statusLine": { "type": "command", "command": "bash \"~/.claude/statusline-command.sh\"" }'

docs:
	$(PYTHON) interfaces/cli/sync_docs.py

sync-cache:
	powershell.exe -ExecutionPolicy Bypass -File interfaces/cli/sync-cache.ps1

sync-plugin-cache:
	powershell.exe -ExecutionPolicy Bypass -File interfaces/cli/sync-plugin-cache.ps1

validate-analysts:
	$(PYTHON) interfaces/cli/validate_analysts.py

setup:
	$(PYTHON) interfaces/cli/setup.py

setup-check:
	$(PYTHON) interfaces/cli/setup.py --check

ci-gate:
	$(PYTHON) interfaces/cli/ci_gate.py

install:
	$(PYTHON) interfaces/cli/generate_routing.py

analytics:
	$(PYTHON) interfaces/cli/ds_analytics/main.py $(if $(PROJECT),--project $(PROJECT),) $(if $(PROJECTS_DIR),--projects-dir $(PROJECTS_DIR),)

dashboard:
	$(PYTHON) interfaces/cli/ds_dashboard.py

dashboard-check:
	$(PYTHON) interfaces/cli/ds_dashboard.py --check

runtime-check:
	$(PYTHON) -m pytest -m runtime_reliability -q

docker-runtime-check:
	docker build -f Dockerfile.runtime-check -t dream-studio-runtime-check .
	docker run --rm --network none -e HOME=/tmp/dream-studio-user -e DREAM_STUDIO_HOME=/tmp/dream-studio-home dream-studio-runtime-check

adapters:
	$(PYTHON) interfaces/cli/build_adapters.py $(if $(PLATFORM),--platform $(PLATFORM),)
