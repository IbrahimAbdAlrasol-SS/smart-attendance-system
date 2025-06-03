"""Development configuration."""
import os
from datetime import timedelta

class DevelopmentConfig:
    """Development configuration class."""
    
    # Basic Flask config
    DEBUG = True
    TESTING = False
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:password@localhost:5432/smart_attendance_dev'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = True  # Log SQL queries in development
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-dev')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/1')
    RATELIMIT_DEFAULT = "100/hour"
    
    # Security Settings
    FACE_RECOGNITION_THRESHOLD = 0.90
    GPS_ACCURACY_METERS = 3
    QR_CODE_EXPIRY_SECONDS = 60
    
    # File Upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    BOT_WEBHOOK_URL = os.getenv('BOT_WEBHOOK_URL')
    BOT_WEBHOOK_PATH = '/api/bot/webhook'
    
    # AI Configuration
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    AI_MODEL_NAME = 'llama3.2'
    
    # Logging
    LOG_LEVEL = 'DEBUG'
    LOG_FILE = 'logs/app.log'
