.PHONY: help venv install dev test lint run tui gui clean

help:
	@echo "Aegis — make targets"
	@echo "  make venv     create .venv and install deps"
	@echo "  make install  editable install with TUI+GUI extras"
	@echo "  make test     run the safety test suite"
	@echo "  make run      launch the interactive CLI"
	@echo "  make tui      launch the TUI"
	@echo "  make gui      launch the GUI"
	@echo "  make doctor   check local model setup"
	@echo "  make lint     byte-compile the package"

venv:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip wheel

install: venv
	./.venv/bin/pip install -e '.[tui,gui]'

dev: venv
	./.venv/bin/pip install -e '.[tui,gui,dev]'

test:
	python3 tests/test_safety.py
	python3 tests/test_agent_loop.py
	python3 tests/test_desktop.py
	python3 tests/test_privacy_rescue.py
	python3 tests/test_setup.py
	python3 tests/test_smart.py
	python3 tests/test_extras.py
	python3 tests/test_streaming.py
	python3 tests/test_bootloader.py
	python3 tests/test_tui_streaming.py
	python3 tests/test_gui_streaming.py
	python3 tests/test_approval.py
	python3 tests/test_allowlist.py
	python3 tests/test_plan.py

snippets:
	python3 -m aegis snippet list

learn:
	python3 -m aegis learn stats

setup:
	python3 -m aegis setup

run:
	python3 -m aegis

tui:
	python3 -m aegis.tui

gui:
	python3 -m aegis.gui

doctor:
	python3 -m aegis doctor

privacy:
	python3 -m aegis privacy status

firstboot-dry:
	python3 -m aegis setup --show --auto

rescue:
	python3 -m aegis rescue scan

lint:
	python3 -m compileall -q aegis && echo "byte-compile ok"

clean:
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
