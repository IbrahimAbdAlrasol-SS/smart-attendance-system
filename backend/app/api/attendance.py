"""Attendance API endpoints."""
from flask import Blueprint
from app.utils.helpers import success_response

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Attendance service is running')

@attendance_bp.route('/', methods=['GET'])
def get_attendance():
    """Get attendance records."""
    return success_response(message='Get attendance endpoint ready')