.PHONY: install dev build clean backend frontend scanner-help

# Detect OS
ifeq ($(OS),Windows_NT)
    IS_WINDOWS = true
    VENV_PYTHON = backend\venv\Scripts\python.exe
    VENV_PIP = backend\venv\Scripts\python.exe -m pip
    RM_RF = rmdir /s /q
    MKDIR = if not exist "$(1)" mkdir "$(1)"
else
    IS_WINDOWS = false
    VENV_PYTHON = backend/venv/bin/python
    VENV_PIP = backend/venv/bin/python -m pip
    RM_RF = rm -rf
    MKDIR = mkdir -p
endif

# Detect python3 binary
ifeq ($(IS_WINDOWS),true)
    PYTHON := $(shell where python 2>nul || where python3 2>nul)
else
    PYTHON := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)
endif

# Install all dependencies
install:
	@echo "Setting up directories..."
ifeq ($(IS_WINDOWS),true)
	@if not exist "data\scans" mkdir "data\scans"
	@if not exist "backend\instance" mkdir "backend\instance"
else
	mkdir -p data/scans backend/instance
endif
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv backend/venv
	@echo "Installing backend dependencies..."
	$(VENV_PIP) install -r backend/requirements.txt
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo ""
	@echo "Setup complete! Run 'make dev' to start."

# Start development servers (backend + frontend)
dev:
ifeq ($(IS_WINDOWS),true)
	powershell -ExecutionPolicy Bypass -File run.ps1
else
	./run.sh
endif

# Start backend only (gunicorn)
backend:
	backend/venv/bin/gunicorn --config backend/gunicorn.conf.py backend.wsgi:app

# Start frontend only
frontend:
	cd frontend && npm start

# Build frontend for production
build:
	cd frontend && npm run build

# Show scanner help
scanner-help:
	$(VENV_PYTHON) scanner/js_scanner.py --help

# Clean build artifacts and caches
clean:
ifeq ($(IS_WINDOWS),true)
	@if exist frontend\build rmdir /s /q frontend\build
	@del /s /q *.pyc 2>nul || (exit /b 0)
else
	rm -rf frontend/build
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
endif
