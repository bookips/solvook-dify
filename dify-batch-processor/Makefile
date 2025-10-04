# Makefile for dify-batch-processor local testing

# Default shell
SHELL := /bin/bash

# --- Configuration ---
LOADER_PORT := 8081
WORKER_PORT := 8082
EMULATOR_PORT := 8080
EMULATOR_HOST_PORT = localhost:$(EMULATOR_PORT)
EMULATOR_PID_FILE := .emulator.pid

# --- Cloud Configuration (for testing deployed resources) ---
GCP_LOCATION ?= asia-northeast3
SCHEDULER_JOB_NAME ?= dify-batch-processor-daily-trigger

# Phony targets (targets that don't represent files)
.PHONY: help all install setup run-emulator stop-emulator run-loader run-worker test-loader test-worker test-deployed clean update-prod-datastore
# Default target
all: help

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Local Development Workflow:"
	@echo "  1. make install          # Install dependencies (run once)"
	@echo "  2. make setup            # Create .env file from .env.example (run once)"
	@echo "  3. make run-emulator-fg  # In Terminal 1, run the Firestore emulator in the foreground"
	@echo "  4. make run-worker       # In Terminal 2, run the worker"
	@echo "  5. make test-worker      # In Terminal 3, test the running worker"
	@echo "  6. make stop-emulator    # In any terminal, stop the emulator when done"
	@echo ""
	@echo "Cloud Testing:"
	@echo "  test-deployed    Trigger the deployed Cloud Scheduler job to run immediately."
	@echo ""
	@echo "Available Targets:"
	@echo "  install          Install python dependencies using poetry."
	@echo "  setup            Create .env file from .env.example if it doesn't exist."
	@echo "  run-emulator-fg  Run Firestore emulator in the foreground. (Requires Java 8+)"
	@echo "  stop-emulator    Stop the running Firestore emulator."
	@echo "  run-loader       Run the loader function on port $(LOADER_PORT)."
	@echo "  run-worker       Run the worker function on port $(WORKER_PORT)."
	@echo "  test-loader      Send a test request to the running loader."
	@echo "  test-worker      Send a test request to the running worker."
	@echo ""
	@echo "Data Management:"
	@echo "  update-prod-datastore ARGS=\"--field status --asis FAILED\"  # Update live GCP Datastore data. (USE WITH CAUTION!)"

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

run-emulator-fg:
	@echo "--> Starting Firestore emulator in Datastore Mode... (Press Ctrl+C to stop)"
	@gcloud beta emulators firestore start --host-port=$(EMULATOR_HOST_PORT) --database-mode=datastore-mode

stop-emulator:
	@echo "--> Attempting to stop Firestore emulator on port $(EMULATOR_PORT)..."
	@PID=$$(lsof -t -i:$(EMULATOR_PORT)); \
	if [ -n "$$PID" ]; then \
		echo "--> Found emulator process with PID: $$PID. Stopping..."; \
		kill $$PID; \
		echo "--> Emulator stopped."; \
	else \
		echo "--> No emulator process found on port $(EMULATOR_PORT)."; \
	fi

run-loader: setup
	@echo "--> Running loader on http://localhost:$(LOADER_PORT)... (Press Ctrl+C to stop)"
	poetry run functions-framework --source=loader/main.py --target=main --port=$(LOADER_PORT)

run-worker: setup
	@echo "--> Running worker on http://localhost:$(WORKER_PORT)... (Press Ctrl+C to stop)"
	poetry run functions-framework --source=worker/main.py --target=main --port=$(WORKER_PORT)
test-loader:
	@echo "--> Sending test request to loader..."
	@curl -w "\n" http://localhost:$(LOADER_PORT)

test-worker:
	@echo "--> Sending test request to worker..."
	@DIFY_ENDPOINT=$$(grep DIFY_API_ENDPOINT .env | cut -d '=' -f2- | tr -d '"'); \
	curl -X POST http://localhost:$(WORKER_PORT) \
	-H "Content-Type: application/json" \
	-d '{ \
		"unique_id": "local-test-from-make", \
		"data": [{"passageId": "local-test-passage-id"}, {"env": "local"}, {"passageGroupId": "local-test-passage-group-id"}], \
		"endpoint": "'$$DIFY_ENDPOINT'" \
	}' \
	-w "\n"

test-deployed:
	@echo "--> Triggering deployed Cloud Scheduler job '$(SCHEDULER_JOB_NAME)' in location '$(GCP_LOCATION)'..."
	@gcloud scheduler jobs run $(SCHEDULER_JOB_NAME) --location $(GCP_LOCATION)
	@echo "--> Job triggered. Check GCP console for logs."

clean:
	@echo "--> Cleaning up emulator PID file..."
	@rm -f $(EMULATOR_PID_FILE)

# --- Data Management ---
 
# Allows passing arguments to the update script.
# Example: make update-prod-datastore ARGS="--field status --asis PROCESSING --tobe PENDING"
update-prod-datastore:
	@echo "Step 1: Authenticating with GCP..."
	gcloud auth application-default login
	@echo "\nStep 2: Running the production update script..."
	@echo "Executing: poetry run python scripts/update_prod_datastore.py $(ARGS)"
	poetry run python scripts/update_prod_datastore.py $(ARGS)