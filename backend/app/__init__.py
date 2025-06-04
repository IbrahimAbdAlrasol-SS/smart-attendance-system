# File: backend/app/__init__.py (complete version)
"""Smart Attendance System - Application Factory."""
import logging
import os
from flask import Flask, jsonify
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
    CORS(app, origins=app.config.get('CORS_ORIGINS', ["*"]))
    
    # Setup logging
    setup_logging(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Setup database
    setup_database(app)
    
    # Add CLI commands
    register_commands(app)
    
    # Add health check
    @app.route('/health')
    def health_check():
        return jsonify({
            'status': 'healthy',
            'service': 'Smart Attendance System',
            'version': '1.0.0'
        })
    
    return app

def register_blueprints(app: Flask) -> None:
    """Register all application blueprints."""
    from app.api.auth import auth_bp
    from app.api.students import students_bp
    from app.api.rooms import rooms_bp
    from app.api.schedules import schedules_bp
    from app.api.lectures import lectures_bp
    from app.api.qr import qr_bp
    from app.api.attendance import attendance_bp
    from app.api.reports import reports_bp
    from app.api.bot_webhook import bot_bp
    
    # Auth
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    
    # Admin Management
    app.register_blueprint(students_bp, url_prefix='/api/admin/students')
    app.register_blueprint(rooms_bp, url_prefix='/api/admin/rooms')
    
    # Core Features
    app.register_blueprint(schedules_bp, url_prefix='/api/schedules')
    app.register_blueprint(lectures_bp, url_prefix='/api/lectures')
    app.register_blueprint(qr_bp, url_prefix='/api/qr')
    app.register_blueprint(attendance_bp, url_prefix='/api/attendance')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    
    # Bot
    app.register_blueprint(bot_bp, url_prefix='/api/bot')
    
    # Swagger UI
    try:
        from flask_swagger_ui import get_swaggerui_blueprint
        from app.utils.swagger import generate_swagger_spec
        
        SWAGGER_URL = '/api/docs'
        API_URL = '/api/swagger.json'
        
        @app.route('/api/swagger.json')
        def swagger_spec():
            """Serve Swagger/OpenAPI specification."""
            return jsonify(generate_swagger_spec())
        
        swaggerui_bp = get_swaggerui_blueprint(
            SWAGGER_URL,
            API_URL,
            config={'app_name': "Smart Attendance System API"}
        )
        app.register_blueprint(swaggerui_bp, url_prefix=SWAGGER_URL)
    except ImportError:
        app.logger.warning("Flask-Swagger-UI not installed")

def register_error_handlers(app: Flask) -> None:
    """Register error handlers."""
    from app.utils.helpers import handle_error
    from flask_jwt_extended import JWTManager
    from werkzeug.exceptions import HTTPException
    
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
        db.session.rollback()
        return handle_error(error, 500)
    
    @app.errorhandler(HTTPException)
    def handle_exception(e):
        return handle_error(e, e.code)
    
    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'error': True,
            'message': 'Token has expired',
            'status_code': 401
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            'error': True,
            'message': 'Invalid token',
            'status_code': 401
        }), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            'error': True,
            'message': 'Authorization token required',
            'status_code': 401
        }), 401

def setup_logging(app: Flask) -> None:
    """Setup application logging."""
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = logging.FileHandler('logs/app.log')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('Smart Attendance System startup')

def setup_database(app: Flask) -> None:
    """Setup database connections."""
    with app.app_context():
        # Import all models
        from app.models import (
            User, UserRole, Section,
            Student, StudyType, StudentStatus,
            Room, Schedule, WeekDay,
            Lecture, AttendanceRecord, AttendanceSession,
            Assignment, SubjectException
        )

def register_commands(app: Flask) -> None:
    """Register CLI commands."""
    import click
    
    @app.cli.command()
    @click.option('--drop', is_flag=True, help='Drop existing tables')
    def init_db(drop):
        """Initialize the database."""
        if drop:
            db.drop_all()
            click.echo('Dropped all tables.')
        
        db.create_all()
        click.echo('Created all tables.')
        
        # Create super admin
        from app.models.user import User, UserRole
        
        super_admin = User.query.filter_by(email='super@admin.com').first()
        if not super_admin:
            super_admin = User(
                email='super@admin.com',
                name='Super Admin',
                role=UserRole.SUPER_ADMIN
            )
            super_admin.set_password('super123456')
            db.session.add(super_admin)
            db.session.commit()
            click.echo('Created super admin user: super@admin.com / super123456')
    
    @app.cli.command()
    def seed_db():
        """Seed database with test data."""
        from app.services.seed_service import SeedService
        
        try:
            SeedService.seed_all()
            click.echo('Database seeded successfully!')
        except Exception as e:
            click.echo(f'Error seeding database: {str(e)}')
    
    @app.cli.command()
    def create_admin():
        """Create admin user."""
        email = click.prompt('Admin email')
        name = click.prompt('Admin name')
        password = click.prompt('Password', hide_input=True)
        
        from app.models.user import User, UserRole
        
        admin = User(
            email=email,
            name=name,
            role=UserRole.ADMIN
        )
        admin.set_password(password)
        
        try:
            db.session.add(admin)
            db.session.commit()
            click.echo(f'Admin user created: {email}')
        except Exception as e:
            db.session.rollback()
            click.echo(f'Error creating admin: {str(e)}')

