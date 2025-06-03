# backend/app/utils/decorators.py
"""Custom decorators for authorization and validation."""
from functools import wraps
from flask_jwt_extended import get_jwt_identity
from app.models.user import User, UserRole
from app.utils.helpers import error_response

def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        if user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return error_response("Admin access required", 403)
        
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    """Decorator to require teacher role or higher."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        if not user.is_teacher():
            return error_response("Teacher access required", 403)
        
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    """Decorator to require student role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        if user.role != UserRole.STUDENT:
            return error_response("Student access required", 403)
        
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """Decorator to require super admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        if user.role != UserRole.SUPER_ADMIN:
            return error_response("Super admin access required", 403)
        
        return f(*args, **kwargs)
    return decorated_function

