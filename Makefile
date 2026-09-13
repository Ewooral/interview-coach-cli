.PHONY: help install install-dev build clean test pipx-install pipx-uninstall publish-test publish bump-version

# Pick whichever Python is available (venv > python3 > python)
PY := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)

help:
	@echo "Interview Coach CLI — build tasks"
	@echo ""
	@echo "  make install         # Install into current venv (editable)"
	@echo "  make install-dev     # Install with dev + gemini extras"
	@echo "  make build           # Build wheel + sdist into dist/"
	@echo "  make clean           # Delete build artefacts"
	@echo "  make pipx-install    # Build wheel and install with pipx (system-wide command)"
	@echo "  make pipx-uninstall  # Remove the pipx install"
	@echo "  make test            # Import smoke test"
	@echo "  make publish-test    # Upload to TestPyPI"
	@echo "  make publish         # Upload to real PyPI"
	@echo "  make bump-version VERSION=0.3.1  # Bump version in both pyproject.toml + main.py"

install:
	pip install -e .

install-dev:
	pip install -e ".[gemini,dev]"

build: clean
	pipx run build

clean:
	rm -rf dist build *.egg-info

test:
	$(PY) -c "import main, providers, coach_graph, meeting_plans, research, screen_capture; print('imports OK')"

pipx-install: build
	pipx install --force ./dist/*.whl

pipx-uninstall:
	pipx uninstall interview-coach-cli

publish-test: build
	pipx run twine upload --repository testpypi dist/*

publish: build
	pipx run twine upload dist/*

bump-version:
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: VERSION not given. Usage: make bump-version VERSION=0.3.1"; \
		exit 1; \
	fi
	@echo "Bumping to $(VERSION)…"
	@sed -i.bak -E 's/^version = ".*"/version = "$(VERSION)"/' pyproject.toml
	@sed -i.bak -E 's/^APP_VERSION = ".*"/APP_VERSION = "$(VERSION)"/' main.py
	@rm -f pyproject.toml.bak main.py.bak
	@grep -E '^version|^APP_VERSION' pyproject.toml main.py
	@echo "✓ Bumped. Run 'make pipx-install' or 'make publish' to release."
