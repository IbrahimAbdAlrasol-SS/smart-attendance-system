"""Lectures API endpoints."""
from flask import Blueprint
from app.utils.helpers import success_response

lectures_bp = Blueprint('lectures', __name__)

@lectures_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Lectures service is running')

@lectures_bp.route('/', methods=['GET'])
def get_lectures():
    """Get all lectures."""
    return success_response(message='Get lectures endpoint ready')