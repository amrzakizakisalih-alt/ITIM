# ── ITIM Makefile ──
# Starts the frontend and the backend (or both together)

.PHONY: all install certs backend frontend dev test stop help

# Default ports
BACKEND_PORT ?= 9000
FRONTEND_PORT ?= 5173

# Commandes Python / Node
PYTHON ?= python3
NPM ?= npm
UVICORN ?= uvicorn

# Local IP detection (for tablet/phone certificate)
LOCAL_IP := $(shell hostname -I 2>/dev/null | awk '{print $$1}')

help: ## Shows help
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Installe toutes les dépendances

certs: ## Generates SSL certificates (mkcert) for localhost and local IP
	@which mkcert >/dev/null 2>&1 || { echo "❌ mkcert n'est pas installé. Installe-le avec : sudo apt install mkcert"; exit 1; }
	@echo "🔐 Generating SSL certificates..."
	@echo "   Detected local IP: $(LOCAL_IP)"
	cd backend && mkcert -cert-file localhost.pem -key-file localhost-key.pem localhost 127.0.0.1 ::1 $(LOCAL_IP)
	cp backend/localhost.pem frontend/localhost.pem
	cp backend/localhost-key.pem frontend/localhost-key.pem
	@echo "✅ Certificates generated. Install rootCA.pem on your iPad/tablet if not already done."

install-backend: ## Installs Python backend dependencies
	@echo "📦 Installation du backend..."
	cd backend && $(PYTHON) -m pip install -r requirements.txt

install-frontend: ## Installs Node frontend dependencies
	@echo "📦 Installation du frontend..."
	cd frontend && $(NPM) install

backend: certs ## Starts the backend (FastAPI/Uvicorn HTTPS)
	@echo "🚀 Starting backend on https://$(LOCAL_IP):$(BACKEND_PORT) ..."
	cd backend && $(PYTHON) -m $(UVICORN) app.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload --ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem

frontend: ## Starts the frontend (Vite dev server HTTPS)
	@echo "🚀 Starting frontend on https://localhost:$(FRONTEND_PORT) ..."
	cd frontend && $(NPM) run dev

dev: certs ## Starts the backend AND the frontend in parallel
	@echo "🚀 Starting backend and frontend simultaneously..."
	@echo "   Backend  → https://$(LOCAL_IP):$(BACKEND_PORT)"
	@echo "   Frontend → https://localhost:$(FRONTEND_PORT)"
	@echo "   Ctrl+C pour tout arrêter"
	@echo ""
	@(trap 'kill 0' 2; \
		cd backend && $(PYTHON) -m $(UVICORN) app.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload --ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem & \
		cd frontend && $(NPM) run dev & \
		wait)

test: ## Runs backend tests
	@echo "🧪 Lancement des tests..."
	cd backend && $(PYTHON) -m pytest -v

stop: ## Stops backend/frontend processes (searches by port)
	@echo "🛑 Arrêt des processus sur les ports $(BACKEND_PORT) et $(FRONTEND_PORT)..."
	@-lsof -ti :$(BACKEND_PORT) | xargs kill -9 2>/dev/null || true
	@-lsof -ti :$(FRONTEND_PORT) | xargs kill -9 2>/dev/null || true
	@echo "✅ Terminé"
