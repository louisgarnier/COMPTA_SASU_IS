# LGC — commandes de développement
# Ports décalés (8001/3001) pour cohabiter avec d'autres projets locaux
# qui occupent souvent 8000/3000 (ex: Stocks). Le front cible le back via
# frontend/.env.local (le rewrite Next (next.config.ts) proxifie /api vers 127.0.0.1:8001).

VENV     := backend/venv
PY       := $(VENV)/bin/python
UVICORN  := $(VENV)/bin/uvicorn
PYTEST   := $(VENV)/bin/pytest
BACK_PORT := 8001
FRONT_PORT := 3001

.PHONY: help install dev back front test test-back test-front seed seed-reset

help:
	@echo "make install    - installe les deps back (venv) + front (npm)"
	@echo "make dev        - lance back (:$(BACK_PORT)) + front (:$(FRONT_PORT)) en parallele"
	@echo "make back       - lance uniquement le back (:$(BACK_PORT))"
	@echo "make front      - lance uniquement le front (:$(FRONT_PORT))"
	@echo "make seed       - remplit la base avec des donnees de demo (si vide)"
	@echo "make seed-reset - vide puis reseed la base de demo"
	@echo "make test       - lance les tests back + front"

seed:
	$(PY) -m backend.seed

seed-reset:
	$(PY) -m backend.seed --reset

install:
	$(PY) -m pip install -r backend/requirements.txt
	cd frontend && npm install

# Lance les deux process ; Ctrl-C arrete les deux (trap sur les PID).
dev:
	@echo "🚀 LGC — back :$(BACK_PORT) + front :$(FRONT_PORT) (Ctrl-C pour arreter)"
	@trap 'kill 0' INT TERM EXIT; \
	$(UVICORN) backend.api.main:app --reload --port $(BACK_PORT) & \
	(cd frontend && npm run dev -- -p $(FRONT_PORT)) & \
	wait

back:
	$(UVICORN) backend.api.main:app --reload --port $(BACK_PORT)

front:
	cd frontend && npm run dev -- -p $(FRONT_PORT)

test: test-back test-front

test-back:
	$(PYTEST)

test-front:
	cd frontend && npm test
