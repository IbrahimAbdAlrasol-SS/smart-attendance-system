# File: backend/app/api/auth.py
"""Authentication API endpoints - Updated for student login."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token, create_refresh_token
from app import db, limiter
from app.models.user import User, UserRole
from app.models.student import Student
from app.utils.helpers import success_response, error_response
from app.services.auth_service import AuthService
from datetime import datetime

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return success_response(message="Auth service is running")

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    """Regular user login (teachers, admins)."""
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

@auth_bp.route("/student-login", methods=["POST"])
@limiter.limit("5 per minute")
def student_login():
    """Student login with university ID and secret code."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        university_id = data.get("university_id", "").strip().upper()
        secret_code = data.get("secret_code", "").strip()
        
        if not university_id or not secret_code:
            return error_response("University ID and secret code are required", 400)
        
        # Find student
        student = Student.query.filter_by(university_id=university_id).first()
        
        if not student:
            return error_response("Invalid credentials", 401)
        
        # Verify secret code
        if not student.verify_secret_code(secret_code):
            return error_response("Invalid credentials", 401)
        
        # Check if student is active
        if student.status != 'active' or not student.user.is_active:
            return error_response("Account is not active", 403)
        
        # Create tokens
        access_token = create_access_token(identity=student.user_id)
        refresh_token = create_refresh_token(identity=student.user_id)
        
        # Update last login
        student.user.last_login = db.func.now()
        db.session.commit()
        
        return success_response(
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "student": student.to_dict(),
                "user": student.user.to_dict()
            },
            message="Login successful"
        )
        
    except Exception as e:
        return error_response(f"Student login error: {str(e)}", 500)

@auth_bp.route("/register-face", methods=["POST"])
@jwt_required()
def register_face():
    """Register face data for first-time use."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if user.role != UserRole.STUDENT:
            return error_response("Only students can register face", 403)
        
        student = user.student_profile
        
        if student.face_registered:
            return error_response("Face already registered", 400)
        
        # Mark face as registered (actual face data stays on device)
        student.face_registered = True
        student.face_registered_at = datetime.utcnow()
        db.session.commit()
        
        return success_response(
            data={
                "face_registered": True,
                "registered_at": student.face_registered_at.isoformat()
            },
            message="Face registered successfully"
        )
        
    except Exception as e:
        return error_response(f"Face registration error: {str(e)}", 500)

@auth_bp.route("/verify-face", methods=["POST"])
@jwt_required()
def verify_face():
    """Verify face recognition result from mobile app."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        
        # Mobile app sends face verification result
        face_verified = data.get("face_verified", False)
        verification_timestamp = data.get("timestamp")
        
        if not isinstance(face_verified, bool):
            return error_response("Invalid face verification data", 400)
        
        # Store verification status in session/cache
        # In production, use Redis for this
        # For now, we just acknowledge the verification
        
        return success_response(
            data={
                "verified": face_verified,
                "user_id": current_user_id,
                "timestamp": verification_timestamp
            },
            message="Face verification recorded"
        )
        
    except Exception as e:
        return error_response(f"Face verification error: {str(e)}", 500)

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    """Get current user profile."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        response_data = user.to_dict()
        
        # Add student profile if user is student
        if user.role == UserRole.STUDENT and hasattr(user, 'student_profile'):
            response_data['student_profile'] = user.student_profile.to_dict()
        
        return success_response(data=response_data)
        
    except Exception as e:
        return error_response(f"Profile error: {str(e)}", 500)
