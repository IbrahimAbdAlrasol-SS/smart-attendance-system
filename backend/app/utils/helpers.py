"""Helper functions for the application."""
from flask import jsonify
from typing import Dict, Any

def handle_error(error, status_code: int):
    """Handle application errors with consistent format."""
    return jsonify({
        'error': True,
        'message': str(error),
        'status_code': status_code
    }), status_code

def success_response(data: Any = None, message: str = "Success"):
    """Return consistent success response."""
    response = {
        'error': False,
        'message': message
    }
    
    if data is not None:
        response['data'] = data
    
    return jsonify(response)

def error_response(message: str, status_code: int = 400):
    """Return consistent error response."""
    return jsonify({
        'error': True,
        'message': message,
        'status_code': status_code
    }), status_code