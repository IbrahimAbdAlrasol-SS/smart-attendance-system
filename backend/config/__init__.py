"""Configuration package - Fixed Version."""
import os

class DevelopmentConfig:
    """Development configuration class."""
    
    DEBUG = True
    TESTING = False
    SECRET_KEY = 'dev-secret-key'
    
    # SQLite فقط للبداية
    SQLALCHEMY_DATABASE_URI = 'sqlite:///smart_attendance.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = True
    
    # تعطيل Redis مؤقتاً
    REDIS_URL = None
    RATELIMIT_ENABLED = False
    
    # JWT بسيط
    JWT_SECRET_KEY = 'jwt-secret'

def get_config(config_name=None):
    """Get configuration instance."""
    return DevelopmentConfig()
