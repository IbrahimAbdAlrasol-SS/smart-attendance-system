"""Testing configuration."""
import os
from datetime import timedelta

class TestingConfig:
    """Testing configuration class."""
    
    # Basic Flask config
    DEBUG = False
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    
    # Database (in-memory SQLite for testing)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # Redis (mock or test Redis)
    REDIS_URL = 'redis://localhost:6379/15'
    
    # JWT Configuration
    JWT_SECRET_KEY = 'test-jwt-secret'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(hours=1)
    
    # Rate Limiting (disabled for testing)
    RATELIMIT_ENABLED = False
    
    # Security Settings (relaxed for testing)
    FACE_RECOGNITION_THRESHOLD = 0.80
    GPS_ACCURACY_METERS = 10
    QR_CODE_EXPIRY_SECONDS = 300
    
    # File Upload
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1MB for testing
    UPLOAD_FOLDER = '/tmp/test_uploads'
    
    # Disable external services in testing
    BOT_TOKEN = 'test-bot-token'
    BOT_WEBHOOK_URL = 'http://localhost:5000/api/bot/webhook'
    
    # Logging
    LOG_LEVEL = 'WARNING'
