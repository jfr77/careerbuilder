.PHONY: dev backend frontend install test

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	.venv/bin/uvicorn backend.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# starts both; Ctrl-C stops both
dev:
	@trap 'kill 0' INT TERM; \
	.venv/bin/uvicorn backend.main:app --reload --port 8000 & \
	(cd frontend && npm run dev) & \
	wait

test:
	.venv/bin/python test_api.py
