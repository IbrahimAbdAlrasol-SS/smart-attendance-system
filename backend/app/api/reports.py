"""Reports API endpoints."""
from flask import Blueprint
from app.utils.helpers import success_response

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Reports service is running')