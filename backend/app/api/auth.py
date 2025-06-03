# تحديث Auth API بالتطبيق الكامل

"""Authentication API endpoints - Full Implementation."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.utils.helpers import success_response, error_response
from app.services.auth_service import AuthService
from app.models.user import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return success_response(message="Auth service is running")

@auth_bp.route("/login", methods=["POST"])
def login():
    """User login endpoint."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        email = data.get("email", "").strip()
        password = data.get("password", "")
        
        if not email or not password:
            return error_response("Email and password are required", 400)
        
        result, error = AuthService.login(email, password)
        
        if error:
            return error_response(error, 401)
        
        return success_response(
            data=result,
            message="Login successful"
        )
        
    except Exception as e:
        return error_response(f"Login error: {str(e)}", 500)

@auth_bp.route("/register", methods=["POST"])
def register():
    """User registration endpoint."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        email = data.get("email", "").strip()
        password = data.get("password", "")
        name = data.get("name", "").strip()
        role = data.get("role", "STUDENT").upper()
        
        result, error = AuthService.register(email, password, name, role)
        
        if error:
            return error_response(error, 400)
        
        return success_response(
            data=result,
            message="Registration successful"
        ), 201
        
    except Exception as e:
        return error_response(f"Registration error: {str(e)}", 500)

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    """Get current user profile."""
    try:
        user_id = get_jwt_identity()
        user = AuthService.get_user_by_id(user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        if not user.is_active:
            return error_response("Account is deactivated", 403)
        
        return success_response(
            data=user.to_dict(),
            message="User profile retrieved"
        )
        
    except Exception as e:
        return error_response(f"Profile error: {str(e)}", 500)

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    try:
        user_id = get_jwt_identity()
        result, error = AuthService.refresh_token(user_id)
        
        if error:
            return error_response(error, 401)
        
        return success_response(
            data=result,
            message="Token refreshed successfully"
        )
        
    except Exception as e:
        return error_response(f"Token refresh error: {str(e)}", 500)

@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """User logout endpoint."""
    # In a full implementation, you would blacklist the token
    # For now, we just return success (client should discard token)
    return success_response(message="Logout successful")
