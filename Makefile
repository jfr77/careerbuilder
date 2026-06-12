.PHONY: dev backend frontend install test

# Backend port: environment beats .env beats the 8787 default.
# Override with `PORT=9001 make dev` or set PORT in .env.
# 8787 avoids 5000/7000 (macOS AirPlay) and 3000/5173 (frontend dev servers).
PORT ?= $(shell sed -n 's/^PORT=//p' .env 2>/dev/null | head -1)
ifeq ($(PORT),)
PORT = 8787
endif

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	.venv/bin/uvicorn backend.main:app --reload --port $(PORT)

frontend:
	cd frontend && VITE_API_URL=http://localhost:$(PORT) npm run dev

# starts both; Ctrl-C stops both
dev:
	@trap 'kill 0' INT TERM; \
	.venv/bin/uvicorn backend.main:app --reload --port $(PORT) & \
	(cd frontend && VITE_API_URL=http://localhost:$(PORT) npm run dev) & \
	wait

test:
	PORT=$(PORT) .venv/bin/python test_api.py
