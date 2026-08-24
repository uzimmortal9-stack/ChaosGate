.PHONY: help install run dev test lint clean docker docker-up docker-down obs k8s-apply k8s-validate dashboard

help:
	@echo "ChaosGate"
	@echo "  make install        create .venv and install dependencies"
	@echo "  make run            start the control plane on :5000"
	@echo "  make test           run the test suite"
	@echo "  make docker-up      docker compose up (gate only)"
	@echo "  make obs            docker compose up with Prometheus + Grafana"
	@echo "  make docker-down    tear the stack down"
	@echo "  make k8s-validate   dry-run the Kubernetes manifests"
	@echo "  make k8s-apply      apply the manifests to the current context"
	@echo "  make dashboard      regenerate the Grafana dashboard + alert rules"
	@echo "  make clean          remove caches and the local database"

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo "done — run 'make run'"

run:
	.venv/bin/python app.py 2>/dev/null || python app.py

dev:
	FLASK_DEBUG=1 .venv/bin/python app.py 2>/dev/null || FLASK_DEBUG=1 python app.py

test:
	.venv/bin/python -m pytest -q 2>/dev/null || python -m pytest -q

lint:
	.venv/bin/python -m compileall -q core app.py
	node --check web/static/js/app.js

docker:
	docker build -t chaosgate/control-plane:latest .

docker-up:
	docker compose up -d --build
	@echo "ChaosGate → http://localhost:5000"

obs:
	docker compose --profile observability up -d --build
	@echo "ChaosGate  → http://localhost:5000"
	@echo "Prometheus → http://localhost:9090"
	@echo "Grafana    → http://localhost:3000 (admin/admin)"

docker-down:
	docker compose --profile observability down

k8s-validate:
	kubectl apply -f k8s/chaosgate.yaml --dry-run=client -o name

k8s-apply:
	kubectl apply -f k8s/chaosgate.yaml
	kubectl -n chaosgate rollout status deploy/chaosgate --timeout=180s

dashboard:
	.venv/bin/python scripts/generate_observability.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache data/chaosgate.db data/artifacts data/workspaces
	@echo "cleaned"
