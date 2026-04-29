.PHONY: test lint fmt security install-dev install-statusline status docs sync-cache

test:
	py -3.12 -m pytest tests/ --cov=hooks/lib --cov=packs/domains/domain_lib --cov-fail-under=70 -q

lint:
	py -3.12 -m black --check . && py -3.12 -m flake8 .

fmt:
	py -3.12 -m black .

security:
	py -3.12 -m pip_audit -r requirements-dev.txt -r requirements.txt

install-dev:
	py -3.12 -m pip install -r requirements-dev.txt && py -3.12 -m pre-commit install

install-statusline:
	@cp scripts/statusline-command.sh "$$HOME/.claude/statusline-command.sh"
	@echo "Copied statusline-command.sh to ~/.claude/"
	@echo "Add to ~/.claude/settings.json:"
	@echo '  "statusLine": { "type": "command", "command": "bash \"~/.claude/statusline-command.sh\"" }'

status:
	@if [ -f hooks/handlers/on-status.py ]; then py -3.12 hooks/handlers/on-status.py; fi

docs:
	py -3.12 scripts/sync_docs.py

sync-cache:
	powershell.exe -ExecutionPolicy Bypass -File scripts/sync-cache.ps1
