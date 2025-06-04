.PHONY: help install dev run test clean db-init db-reset docker-up docker-down

# Default target
help:
	@echo "Smart Attendance System - Available Commands"
	@echo "==========================================="
	@echo "make install    - Install production dependencies"
	@echo "make dev        - Install development dependencies"
	@echo "make run        - Run development server"
	@echo "make test       - Run tests"
	@echo "make db-init    - Initialize database"
	@echo "make db-reset   - Reset database"
	@echo "make seed       - Seed database with test data"
	@echo "make docker-up  - Start Docker containers"
	@echo "make docker-down - Stop Docker containers"
	@echo "make clean      - Clean temporary files"

# Installation
install:
	pip install -r requirements.txt

dev:
	pip install -r requirements.txt
	pip install pytest pytest-cov black flake8

# Development
run:
	python run.py

test:
	pytest -v --cov=app tests/

# Database
db-init:
	flask init-db

db-reset:
	flask reset-db

seed:
	flask seed-all

# Docker
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	rm -rf .coverage htmlcov/
	rm -rf logs/*.log