# Makefile for dify-batch-processor local testing

# Default shell
SHELL := /bin/bash

# --- Configuration ---
LOADER_PORT := 8081
WORKER_PORT := 8082
EMULATOR_PORT := 8080
EMULATOR_HOST_PORT = localhost:$(EMULATOR_PORT)
EMULATOR_PID_FILE := .emulator.pid

# Phony targets (targets that don't represent files)
.PHONY: help all install setup run-emulator stop-emulator run-loader run-worker test-loader test-worker clean

# Default target
all: help

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Local Development Workflow:"
	@echo "  1. make install    # Install dependencies (run once)"
	@echo "  2. make setup      # Create .env file from .env.example (run once)"
	@echo "  3. make run-emulator # Start Firestore emulator in a separate terminal"
	@echo "  4. make run-worker   # Run worker in another terminal"
	@echo "  5. make test-worker  # Test worker from a third terminal"
	@echo "  6. make run-loader   # Run loader in another terminal"
	@echo "  7. make test-loader  # Test loader from a third terminal"
	@echo "  8. make stop-emulator# Stop emulator when done"
	@echo ""
	@echo "Available Targets:"
	@echo "  install          Install python dependencies using poetry."
	@echo "  setup            Create .env file from .env.example if it doesn't exist."
	@echo "  run-emulator     Start Firestore emulator in the background."
	@echo "  stop-emulator    Stop the background Firestore emulator."
	@echo "  run-loader       Run the loader function on port $(LOADER_PORT)."
	@echo "  run-worker       Run the worker function on port $(WORKER_PORT)."
	@echo "  test-loader      Send a test request to the running loader."
	@echo "  test-worker      Send a test request to the running worker."
	@echo "  clean            Remove emulator pid file."

install:
	@echo "--> Installing dependencies using poetry..."
	poetry install

setup:
	@if [ ! -f .env ]; then \
		echo "--> .env file not found. Creating from .env.example..."; \
		cp .env.example .env; \
		echo "--> SUCCESS: .env file created. Please edit it with your actual configuration."; \
	else \
		echo "--> .env file already exists. Skipping creation."; \
	fi

run-emulator:
	@if [ -f $(EMULATOR_PID_FILE) ]; then \
		echo "--> Firestore emulator is already running with PID: $$(cat $(EMULATOR_PID_FILE))."; \
		exit 0; \
	fi
	@echo "--> Starting Firestore emulator on $(EMULATOR_HOST_PORT)..."
	@gcloud beta emulators firestore start --host-port=$(EMULATOR_HOST_PORT) > /dev/null 2>&1 & echo $$! > $(EMULATOR_PID_FILE)
	@echo "--> Firestore emulator started with PID: $$(cat $(EMULATOR_PID_FILE)). Use 'make stop-emulator' to stop it."

stop-emulator:
	@if [ -f $(EMULATOR_PID_FILE) ]; then \
		echo "--> Stopping Firestore emulator (PID: $$(cat $(EMULATOR_PID_FILE)))"; \
		kill $$(cat $(EMULATOR_PID_FILE)); \
		rm $(EMULATOR_PID_FILE); \
		echo "--> Emulator stopped."; \
	else \
		echo "--> Emulator PID file not found. It seems the emulator is not running."; \
	fi

run-loader: setup
	@echo "--> Running loader on http://localhost:$(LOADER_PORT)... (Press Ctrl+C to stop)"
	@export $$(grep -v '^#' .env | xargs) && \
	poetry run functions-framework --source=loader/main.py --target=main --port=$(LOADER_PORT)

run-worker: setup
	@echo "--> Running worker on http://localhost:$(WORKER_PORT)... (Press Ctrl+C to stop)"
	@export $$(grep -v '^#' .env | xargs) && \
	poetry run functions-framework --source=worker/main.py --target=main --port=$(WORKER_PORT)

test-loader:
	@echo "--> Sending test request to loader..."
	@curl -w "\n" http://localhost:$(LOADER_PORT)

test-worker:
	@echo "--> Sending test request to worker..."
	@DIFY_ENDPOINT=$$(grep DIFY_API_ENDPOINT .env | cut -d '=' -f2- | tr -d '"'); \
	curl -X POST http://localhost:$(WORK_PORT) \
	-H "Content-Type: application/json" \
	-d '{ \
		"unique_id": "local-test-from-make", \
		"data": ["This is a local test query from Makefile."], \
		"endpoint": "'$$DIFY_ENDPOINT'" \
	}' \
	-w "\n"

clean:
	@echo "--> Cleaning up emulator PID file..."
	@rm -f $(EMULATOR_PID_FILE)
