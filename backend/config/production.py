"""Production configuration."""
import os
from datetime import timedelta

class ProductionConfig:
    """Production configuration class."""
    
    # Basic Flask config
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.getenv('SECRET_KEY')  # Must be set in production
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL')
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    
    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL')
    RATELIMIT_DEFAULT = "50/hour"
    
    # Security Settings
    FACE_RECOGNITION_THRESHOLD = 0.95
    GPS_ACCURACY_METERS = 2
    QR_CODE_EXPIRY_SECONDS = 30
    
    # File Upload
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8MB in production
    UPLOAD_FOLDER = '/app/uploads'
    
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    BOT_WEBHOOK_URL = os.getenv('BOT_WEBHOOK_URL')
    BOT_WEBHOOK_PATH = '/api/bot/webhook'
    
    # AI Configuration
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
    AI_MODEL_NAME = os.getenv('AI_MODEL_NAME', 'llama3.2')
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = '/app/logs/app.log'
