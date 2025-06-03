"""Authentication API endpoints."""
from flask import Blueprint, request, jsonify
from app.utils.helpers import success_response, error_response

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Auth service is running')

@auth_bp.route('/login', methods=['POST'])
def login():
    """User login endpoint."""
    return success_response(message='Login endpoint ready')

@auth_bp.route('/register', methods=['POST'])
def register():
    """User registration endpoint."""
    return success_response(message='Registration endpoint ready')