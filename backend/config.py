# File: backend/config.py
"""Configuration module for Smart Attendance System."""
import os
from datetime import timedelta

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_ALGORITHM = 'HS256'
    
    # CORS
    CORS_ORIGINS = ["http://localhost:*", "https://*.vercel.app", "http://127.0.0.1:*"]
    
    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL') or 'memory://'
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    
    # Security
    FACE_RECOGNITION_THRESHOLD = 0.90
    GPS_ACCURACY_METERS = 3
    QR_CODE_DEFAULT_EXPIRY = 60  # seconds
    QR_CODE_MAX_EXPIRY = 300  # 5 minutes
    
    # Attendance
    ATTENDANCE_VERIFICATION_TOKEN_EXPIRY = 120  # seconds
    EXCEPTIONAL_ATTENDANCE_AUTO_APPROVE = False
    
    # File Upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
    
    # Pagination
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///smart_attendance_dev.db'
    SQLALCHEMY_ECHO = True
    
    # Redis (optional in dev)
    REDIS_URL = os.environ.get('REDIS_URL') or None

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # Redis (required in production)
    REDIS_URL = os.environ.get('REDIS_URL')
    
    # Enhanced security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Stricter limits
    RATELIMIT_DEFAULT = "100 per day, 20 per hour"

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    RATELIMIT_ENABLED = False

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config(config_name=None):
    """Get configuration by name."""
    return config.get(config_name or os.environ.get('FLASK_ENV', 'default'))
