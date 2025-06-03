"""Smart Attendance System - Application Factory."""
import logging
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

def create_app(config_name: str = None) -> Flask:
    """Application factory pattern."""
    app = Flask(__name__)
    
    # Load configuration
    from config import get_config
    config_class = get_config(config_name)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    
    # Configure CORS
    CORS(app, origins=["http://localhost:*", " https://*.vercel.app "])
    
    # Setup logging
    setup_logging(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Setup database
    setup_database(app)
    
    return app

def register_blueprints(app: Flask) -> None:
    """Register application blueprints."""
    from app.api.auth import auth_bp
    from app.api.lectures import lectures_bp
    from app.api.attendance import attendance_bp
    from app.api.reports import reports_bp
    from app.api.bot_webhook import bot_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(lectures_bp, url_prefix='/api/lectures')
    app.register_blueprint(attendance_bp, url_prefix='/api/attendance')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(bot_bp, url_prefix='/api/bot')

def register_error_handlers(app: Flask) -> None:
    """Register error handlers."""
    from app.utils.helpers import handle_error
    
    @app.errorhandler(400)
    def bad_request(error):
        return handle_error(error, 400)
    
    @app.errorhandler(401)
    def unauthorized(error):
        return handle_error(error, 401)
    
    @app.errorhandler(403)
    def forbidden(error):
        return handle_error(error, 403)
    
    @app.errorhandler(404)
    def not_found(error):
        return handle_error(error, 404)
    
    @app.errorhandler(500)
    def internal_error(error):
        return handle_error(error, 500)

def setup_logging(app: Flask) -> None:
    """Setup application logging."""
    if not app.debug and not app.testing:
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        # Setup file handler
        file_handler = logging.FileHandler('logs/app.log')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('Smart Attendance System startup')

def setup_database(app: Flask) -> None:
    """Setup database connections without creating tables automatically."""
    with app.app_context():
        # Import all models to ensure they're registered
        from app.models import user, lecture, attendance, assignment
        
        # Don't create tables automatically - use flask commands instead
        pass