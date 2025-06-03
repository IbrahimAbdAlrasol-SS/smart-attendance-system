# Smart Attendance System - PowerShell Scripts

function Show-Help {
    Write-Host "Smart Attendance System - Development Commands" -ForegroundColor Green
    Write-Host "=============================================="
    Write-Host ".\scripts.ps1 setup          - Complete setup (install + db-setup)"
    Write-Host ".\scripts.ps1 install        - Install production dependencies"
    Write-Host ".\scripts.ps1 dev-install    - Install development dependencies"
    Write-Host ".\scripts.ps1 run            - Run development server"
    Write-Host ".\scripts.ps1 test           - Run tests"
    Write-Host ".\scripts.ps1 db-setup       - Setup database with sample data"
    Write-Host ".\scripts.ps1 db-reset       - Reset database completely"
    Write-Host ".\scripts.ps1 docker-up      - Start PostgreSQL and Redis with Docker"
    Write-Host ".\scripts.ps1 docker-down    - Stop Docker containers"
    Write-Host ".\scripts.ps1 clean          - Clean temporary files"
}

function Install-Deps {
    pip install -r requirements.txt
}

function Install-DevDeps {
    pip install -r requirements-dev.txt
}

function Setup-Complete {
    Write-Host "?? Starting complete setup..." -ForegroundColor Yellow
    Install-DevDeps
    Docker-Up
    Start-Sleep -Seconds 8
    Database-Setup
    Write-Host "? Complete setup finished!" -ForegroundColor Green
}

function Docker-Up {
    Write-Host "?? Starting Docker containers..." -ForegroundColor Blue
    docker-compose up -d postgres redis
    Write-Host " Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}

function Docker-Down {
    docker-compose down
}

function Database-Setup {
    Write-Host " Setting up database..." -ForegroundColor Blue
    flask create-db
    flask init-db
}

function Database-Reset {
    flask reset-db
    flask init-db
}

function Run-Server {
    python run.py
}

function Run-Tests {
    pytest -v --cov=app tests/
}

function Clean-Files {
    Get-ChildItem -Path . -Include "*.pyc" -Recurse | Remove-Item -Force
    Get-ChildItem -Path . -Include "__pycache__" -Recurse | Remove-Item -Force -Recurse
    Get-ChildItem -Path . -Include ".pytest_cache" -Recurse | Remove-Item -Force -Recurse
    if (Test-Path ".coverage") { Remove-Item ".coverage" -Force }
    if (Test-Path "htmlcov") { Remove-Item "htmlcov" -Force -Recurse }
}

# Main script logic
switch (\[0]) {
    "help" { Show-Help }
    "install" { Install-Deps }
    "dev-install" { Install-DevDeps }
    "setup" { Setup-Complete }
    "docker-up" { Docker-Up }
    "docker-down" { Docker-Down }
    "db-setup" { Database-Setup }
    "db-reset" { Database-Reset }
    "run" { Run-Server }
    "test" { Run-Tests }
    "clean" { Clean-Files }
    default {
        Write-Host "Unknown command. Use '.\scripts.ps1 help' for available commands." -ForegroundColor Red
        Show-Help
    }
}
