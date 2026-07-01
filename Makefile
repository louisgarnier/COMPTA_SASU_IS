# LGC — commandes de développement
# `make dev` lance back (FastAPI :8000) + front (Next.js :3000) ensemble.

VENV    := backend/venv
PY      := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
PYTEST  := $(VENV)/bin/pytest

.PHONY: help install dev back front test test-back test-front

help:
	@echo "make install    - installe les deps back (venv) + front (npm)"
	@echo "make dev        - lance back (:8000) + front (:3000) en parallele"
	@echo "make back       - lance uniquement le back (:8000)"
	@echo "make front      - lance uniquement le front (:3000)"
	@echo "make test       - lance les tests back + front"

install:
	$(PY) -m pip install -r backend/requirements.txt
	cd frontend && npm install

# Lance les deux process ; Ctrl-C arrete les deux (trap sur les PID).
dev:
	@echo "🚀 LGC — back :8000 + front :3000 (Ctrl-C pour arreter)"
	@trap 'kill 0' INT TERM EXIT; \
	$(UVICORN) backend.api.main:app --reload --port 8000 & \
	(cd frontend && npm run dev) & \
	wait

back:
	$(UVICORN) backend.api.main:app --reload --port 8000

front:
	cd frontend && npm run dev

test: test-back test-front

test-back:
	$(PYTEST)

test-front:
	cd frontend && npm test
