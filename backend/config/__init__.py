"""Configuration package for the Smart Attendance System."""
import os
from typing import Type

from .development import DevelopmentConfig
from .production import ProductionConfig
from .testing import TestingConfig

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config(config_name: str = None) -> Type:
    """Get configuration class based on environment."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')
    
    return config_map.get(config_name, config_map['default'])
