.PHONY: help install dev-install test clean setup db-setup db-reset run 

# Help 
help: 
 @echo "Smart Attendance System - Development Commands" 
 @echo "==============================================" 
 @echo "setup          - Complete setup (install + db-setup)" 
 @echo "install        - Install production dependencies" 
 @echo "dev-install    - Install development dependencies" 
 @echo "run            - Run development server" 
 @echo "test           - Run tests" 
 @echo "db-setup       - Setup database with sample data" 
 @echo "db-reset       - Reset database completely" 
 @echo "docker-up      - Start PostgreSQL and Redis with Docker" 
 @echo "docker-down    - Stop Docker containers" 
 @echo "clean          - Clean temporary files" 

# Setup 
setup: dev-install docker-up db-setup 
 @echo " Complete setup finished!" 

# Installation 
install: 
 pip install -r requirements.txt 

dev-install: 
 pip install -r requirements-dev.txt 

# Database 
db-setup: 
 flask create-db 
 flask init-db 

db-reset: 
 flask reset-db 
 flask init-db 

# Docker 
docker-up: 
 docker-compose up -d postgres redis 
 @echo " Waiting for PostgreSQL to be ready..." 
 @sleep 5 

docker-down: 
 docker-compose down 

# Development 
run: 
 python run.py 

test: 
 pytest -v --cov=app tests/ 

# Cleanup 
clean: 
 find . -type f -name "*.pyc" -delete 
 find . -type d -name "__pycache__" -delete 
 find . -type d -name ".pytest_cache" -delete 
 rm -rf .coverage htmlcov/ 
