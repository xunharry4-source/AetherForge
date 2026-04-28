PYTHON = ./.venv/bin/python
PIP = $(PYTHON) -m pip
SYSTEM_PYTHON = python3.12
FRONTEND_DIR = frontend
UI_DIR = ui

.PHONY: help install start stop restart status clean

help:
	@echo "Novel Agent - Management Commands:"
	@echo "  make install  - Create venv (.venv) and install dependencies"
	@echo "  make start    - Run backend, NiceGUI UI, and Vite frontend in foreground"
	@echo "  make stop     - Kill background processes"
	@echo "  make restart  - Stop and start again"
	@echo "  make status   - Check if processes are running"
	@echo "  make clean    - Remove log files and pid files"

install:
	@echo "📦 Creating virtual environment (.venv) using $(SYSTEM_PYTHON)..."
	@if [ -d ".venv" ] && { [ ! -x "$(PYTHON)" ] || ! (unset PYTHONPATH; unset PYTHONHOME; $(PYTHON) -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'); }; then \
		echo "⚠️ Existing .venv is invalid or not Python 3.12; rebuilding..."; \
		rm -rf .venv; \
	fi
	@if [ ! -d ".venv" ]; then \
		unset PYTHONPATH && unset PYTHONHOME && $(SYSTEM_PYTHON) -m venv .venv; \
	fi
	@echo "📦 Installing Backend dependencies..."
	@unset PYTHONPATH && unset PYTHONHOME && $(PIP) install --upgrade pip
	@unset PYTHONPATH && unset PYTHONHOME && $(PIP) install -r requirements.txt || echo "⚠️ Pip install failed. Please check network/dependencies."
	@echo "📦 Checking Frontend dependencies in $(FRONTEND_DIR)..."
	@if [ -d "$(FRONTEND_DIR)" ] && [ -f "$(FRONTEND_DIR)/package.json" ]; then \
		echo "📦 Installing Frontend dependencies (npm install)..."; \
		(cd $(FRONTEND_DIR) && npm install) || echo "⚠️ npm install failed. Please check your Node.js environment."; \
	else \
		echo "⚠️ Skipping frontend install: $(FRONTEND_DIR)/package.json not found."; \
	fi

start:
	@mkdir -p logs
	@echo "🚀 Starting all services in foreground (Press Ctrl+C to stop)..."
	@/bin/bash -c "EXIT_HANDLED=0; trap 'if [ \$$EXIT_HANDLED -eq 0 ]; then echo -e \"\n🛑 Stopping services...\"; EXIT_HANDLED=1; kill 0; fi' SIGINT SIGTERM EXIT; \
		env PYTHONPATH=.:src:src/common $(PYTHON) app_api.py 2>&1 | tee logs/backend.log & echo \$$! > $(CURDIR)/.backend.pid; \
		env PYTHONPATH=.:src:src/common $(PYTHON) $(UI_DIR)/main.py 2>&1 | tee logs/ui.log & echo \$$! > $(CURDIR)/.ui.pid; \
		if [ -f \"$(FRONTEND_DIR)/package.json\" ]; then \
			cd $(FRONTEND_DIR) && npm run dev 2>&1 | tee ../logs/frontend.log & echo \$$! > $(CURDIR)/.frontend.pid; \
		fi; \
		wait"

stop:
	@echo "🛑 Stopping Backend..."
	@if [ -f .backend.pid ]; then kill $$(cat .backend.pid) 2>/dev/null || true; rm .backend.pid; fi
	@echo "🛑 Stopping Admin UI..."
	@if [ -f .ui.pid ]; then kill $$(cat .ui.pid) 2>/dev/null || true; rm .ui.pid; fi
	@echo "🛑 Stopping Frontend..."
	@if [ -f .frontend.pid ]; then kill $$(cat .frontend.pid) 2>/dev/null || true; rm .frontend.pid; fi
	@echo "✅ All processes stopped."

restart: stop start

status:
	@if [ -f .backend.pid ]; then \
		if ps -p $$(cat .backend.pid) > /dev/null; then \
			echo "🟢 Backend: Running (PID $$(cat .backend.pid))"; \
		else \
			echo "🔴 Backend: PID file exists but process is DEAD"; \
		fi \
	else \
		echo "⚪️ Backend: Stopped"; \
	fi
	@if [ -f .ui.pid ]; then \
		if ps -p $$(cat .ui.pid) > /dev/null; then \
			echo "🟢 Admin UI (NiceGUI): Running (PID $$(cat .ui.pid))"; \
		else \
			echo "🔴 Admin UI (NiceGUI): PID file exists but process is DEAD"; \
		fi \
	else \
		echo "⚪️ Admin UI: Stopped"; \
	fi
	@if [ -f .frontend.pid ]; then \
		if ps -p $$(cat .frontend.pid) > /dev/null; then \
			echo "🟢 Frontend (Vite): Running (PID $$(cat .frontend.pid))"; \
		else \
			echo "🔴 Frontend (Vite): PID file exists but process is DEAD"; \
		fi \
	else \
		if [ ! -f "$(FRONTEND_DIR)/package.json" ]; then \
			echo "⚪️ Frontend: Stopped (Missing package.json)"; \
		else \
			echo "⚪️ Frontend: Stopped"; \
		fi \
	fi

clean:
	@echo "🧹 Cleaning logs and pid files..."
	rm -rf logs/*.log
	rm -f .backend.pid .ui.pid .frontend.pid
