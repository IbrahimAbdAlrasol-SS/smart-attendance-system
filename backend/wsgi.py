"""WSGI configuration for production deployment."""
import os
from app import create_app

# Create Flask application instance
app = create_app(os.getenv('FLASK_ENV', 'production'))

if __name__ == "__main__":
    app.run()