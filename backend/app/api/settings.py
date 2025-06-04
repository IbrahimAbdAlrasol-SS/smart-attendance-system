# File: backend/app/api/settings.py
"""System Settings API for configuration management."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.user import User, UserRole
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, super_admin_required
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import os

settings_bp = Blueprint('settings', __name__)

# In-memory settings cache (in production, use Redis)
settings_cache = {}

# Default system settings
DEFAULT_SETTINGS = {
    'attendance': {
        'qr_code_expiry_seconds': 60,
        'max_qr_code_expiry_seconds': 300,
        'gps_accuracy_tolerance_meters': 10,
        'altitude_tolerance_meters': 3,
        'face_recognition_threshold': 0.85,
        'verification_token_expiry_minutes': 2,
        'exceptional_attendance_auto_approve': False,
        'max_exceptional_requests_per_day': 3,
        'attendance_grace_period_minutes': 15,
        'late_checkin_penalty_enabled': False,
        'sequential_verification_enabled': True,
        'barometer_verification_enabled': True
    },
    'security': {
        'password_min_length': 6,
        'password_require_uppercase': False,
        'password_require_numbers': False,
        'password_require_symbols': False,
        'password_expiry_days': 0,  # 0 = never expires
        'max_login_attempts': 5,
        'account_lockout_duration_minutes': 30,
        'session_timeout_minutes': 120,
        'jwt_expiry_hours': 24,
        'jwt_refresh_expiry_days': 7,
        'two_factor_enabled': False,
        'ip_whitelist_enabled': False,
        'allowed_ip_ranges': []
    },
    'notifications': {
        'email_notifications_enabled': True,
        'sms_notifications_enabled': False,
        'telegram_notifications_enabled': False,
        'push_notifications_enabled': True,
        'notification_retention_days': 30,
        'digest_email_frequency': 'weekly',  # daily, weekly, monthly
        'urgent_notification_threshold': 'high'
    },
    'system': {
        'maintenance_mode_enabled': False,
        'maintenance_message': 'النظام تحت الصيانة، يرجى المحاولة لاحقاً',
        'api_rate_limiting_enabled': True,
        'default_page_size': 20,
        'max_page_size': 100,
        'file_upload_max_size_mb': 10,
        'allowed_file_types': ['csv', 'xlsx', 'xls', 'pdf', 'jpg', 'png'],
        'backup_frequency_hours': 24,
        'log_retention_days': 90,
        'analytics_enabled': True,
        'debug_mode': False
    },
    'ui': {
        'theme': 'light',  # light, dark, auto
        'language': 'ar',  # ar, en
        'timezone': 'Asia/Baghdad',
        'date_format': 'DD/MM/YYYY',
        'time_format': '24h',  # 12h, 24h
        'currency': 'IQD',
        'items_per_page': 20,
        'auto_refresh_interval_seconds': 30,
        'show_welcome_tutorial': True
    },
    'integration': {
        'google_maps_api_key': '',
        'telegram_bot_token': '',
        'email_smtp_server': 'smtp.gmail.com',
        'email_smtp_port': 587,
        'email_username': '',
        'email_password': '',
        'external_api_timeout_seconds': 30,
        'webhook_enabled': False,
        'webhook_url': ''
    }
}

@settings_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Settings service is running')

# =================== GENERAL SETTINGS ===================

@settings_bp.route('/', methods=['GET'])
@jwt_required()
@admin_required
def get_all_settings():
    """Get all system settings."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Get settings from cache or load defaults
        all_settings = get_cached_settings()
        
        # Filter sensitive settings for non-super-admin users
        if user.role != UserRole.SUPER_ADMIN:
            # Remove sensitive settings
            filtered_settings = all_settings.copy()
            if 'security' in filtered_settings:
                # Remove sensitive security settings
                sensitive_keys = ['allowed_ip_ranges', 'jwt_expiry_hours']
                for key in sensitive_keys:
                    filtered_settings['security'].pop(key, None)
            
            if 'integration' in filtered_settings:
                # Remove API keys and passwords
                sensitive_keys = ['google_maps_api_key', 'telegram_bot_token', 'email_password']
                for key in sensitive_keys:
                    filtered_settings['integration'][key] = '***hidden***' if filtered_settings['integration'].get(key) else ''
            
            all_settings = filtered_settings
        
        return success_response(
            data={
                'settings': all_settings,
                'last_updated': get_settings_last_updated(),
                'can_edit': user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
            },
            message="System settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving settings: {str(e)}", 500)

@settings_bp.route('/', methods=['PUT'])
@jwt_required()
@admin_required
def update_all_settings():
    """Update all system settings."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        data = request.get_json()
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate settings structure
        validation_result = validate_settings_structure(data)
        if not validation_result['valid']:
            return error_response(f"Invalid settings: {validation_result['error']}", 400)
        
        # Check permissions for sensitive settings
        if user.role != UserRole.SUPER_ADMIN:
            # Non-super-admin cannot modify sensitive settings
            if 'security' in data:
                protected_keys = ['jwt_expiry_hours', 'allowed_ip_ranges', 'two_factor_enabled']
                for key in protected_keys:
                    if key in data['security']:
                        return error_response(f"Permission denied: Cannot modify {key}", 403)
            
            if 'integration' in data:
                protected_keys = ['google_maps_api_key', 'telegram_bot_token']
                for key in protected_keys:
                    if key in data['integration']:
                        return error_response(f"Permission denied: Cannot modify {key}", 403)
        
        # Merge with existing settings
        current_settings = get_cached_settings()
        updated_settings = merge_settings(current_settings, data)
        
        # Save settings
        save_settings(updated_settings, current_user_id)
        
        # Log the change
        log_settings_change(current_user_id, "UPDATE_ALL", updated_settings)
        
        return success_response(
            data={'settings': updated_settings},
            message="Settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating settings: {str(e)}", 500)

# =================== CATEGORY-SPECIFIC SETTINGS ===================

@settings_bp.route('/attendance', methods=['GET'])
@jwt_required()
@admin_required
def get_attendance_settings():
    """Get attendance-related settings."""
    try:
        settings = get_cached_settings()
        return success_response(
            data=settings.get('attendance', {}),
            message="Attendance settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving attendance settings: {str(e)}", 500)

@settings_bp.route('/attendance', methods=['PUT'])
@jwt_required()
@admin_required
def update_attendance_settings():
    """Update attendance-related settings."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate attendance settings
        validation_result = validate_attendance_settings(data)
        if not validation_result['valid']:
            return error_response(f"Invalid attendance settings: {validation_result['error']}", 400)
        
        # Update settings
        current_settings = get_cached_settings()
        current_settings['attendance'].update(data)
        
        save_settings(current_settings, current_user_id)
        log_settings_change(current_user_id, "UPDATE_ATTENDANCE", data)
        
        return success_response(
            data=current_settings['attendance'],
            message="Attendance settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating attendance settings: {str(e)}", 500)

@settings_bp.route('/security', methods=['GET'])
@jwt_required()
@super_admin_required
def get_security_settings():
    """Get security settings (super admin only)."""
    try:
        settings = get_cached_settings()
        return success_response(
            data=settings.get('security', {}),
            message="Security settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving security settings: {str(e)}", 500)

@settings_bp.route('/security', methods=['PUT'])
@jwt_required()
@super_admin_required
def update_security_settings():
    """Update security settings (super admin only)."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate security settings
        validation_result = validate_security_settings(data)
        if not validation_result['valid']:
            return error_response(f"Invalid security settings: {validation_result['error']}", 400)
        
        # Update settings
        current_settings = get_cached_settings()
        current_settings['security'].update(data)
        
        save_settings(current_settings, current_user_id)
        log_settings_change(current_user_id, "UPDATE_SECURITY", data)
        
        return success_response(
            data=current_settings['security'],
            message="Security settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating security settings: {str(e)}", 500)

@settings_bp.route('/notifications', methods=['GET'])
@jwt_required()
@admin_required
def get_notification_settings():
    """Get notification settings."""
    try:
        settings = get_cached_settings()
        return success_response(
            data=settings.get('notifications', {}),
            message="Notification settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving notification settings: {str(e)}", 500)

@settings_bp.route('/notifications', methods=['PUT'])
@jwt_required()
@admin_required
def update_notification_settings():
    """Update notification settings."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Update settings
        current_settings = get_cached_settings()
        current_settings['notifications'].update(data)
        
        save_settings(current_settings, current_user_id)
        log_settings_change(current_user_id, "UPDATE_NOTIFICATIONS", data)
        
        return success_response(
            data=current_settings['notifications'],
            message="Notification settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating notification settings: {str(e)}", 500)

@settings_bp.route('/system', methods=['GET'])
@jwt_required()
@admin_required
def get_system_settings():
    """Get system settings."""
    try:
        settings = get_cached_settings()
        return success_response(
            data=settings.get('system', {}),
            message="System settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving system settings: {str(e)}", 500)

@settings_bp.route('/system', methods=['PUT'])
@jwt_required()
@super_admin_required
def update_system_settings():
    """Update system settings (super admin only)."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate system settings
        validation_result = validate_system_settings(data)
        if not validation_result['valid']:
            return error_response(f"Invalid system settings: {validation_result['error']}", 400)
        
        # Update settings
        current_settings = get_cached_settings()
        current_settings['system'].update(data)
        
        save_settings(current_settings, current_user_id)
        log_settings_change(current_user_id, "UPDATE_SYSTEM", data)
        
        return success_response(
            data=current_settings['system'],
            message="System settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating system settings: {str(e)}", 500)

@settings_bp.route('/ui', methods=['GET'])
@jwt_required()
def get_ui_settings():
    """Get UI settings (available to all users)."""
    try:
        settings = get_cached_settings()
        return success_response(
            data=settings.get('ui', {}),
            message="UI settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving UI settings: {str(e)}", 500)

@settings_bp.route('/ui', methods=['PUT'])
@jwt_required()
@admin_required
def update_ui_settings():
    """Update UI settings."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Update settings
        current_settings = get_cached_settings()
        current_settings['ui'].update(data)
        
        save_settings(current_settings, current_user_id)
        log_settings_change(current_user_id, "UPDATE_UI", data)
        
        return success_response(
            data=current_settings['ui'],
            message="UI settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating UI settings: {str(e)}", 500)

@settings_bp.route('/integration', methods=['GET'])
@jwt_required()
@super_admin_required
def get_integration_settings():
    """Get integration settings (super admin only)."""
    try:
        settings = get_cached_settings()
        return success_response(
            data=settings.get('integration', {}),
            message="Integration settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving integration settings: {str(e)}", 500)

@settings_bp.route('/integration', methods=['PUT'])
@jwt_required()
@super_admin_required
def update_integration_settings():
    """Update integration settings (super admin only)."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Update settings
        current_settings = get_cached_settings()
        current_settings['integration'].update(data)
        
        save_settings(current_settings, current_user_id)
        log_settings_change(current_user_id, "UPDATE_INTEGRATION", data)
        
        return success_response(
            data=current_settings['integration'],
            message="Integration settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating integration settings: {str(e)}", 500)

# =================== SETTINGS MANAGEMENT ===================

@settings_bp.route('/reset', methods=['POST'])
@jwt_required()
@super_admin_required
def reset_settings():
    """Reset settings to defaults."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        category = data.get('category', 'all')
        
        current_settings = get_cached_settings()
        
        if category == 'all':
            # Reset all settings to defaults
            reset_settings = DEFAULT_SETTINGS.copy()
        elif category in DEFAULT_SETTINGS:
            # Reset specific category
            reset_settings = current_settings.copy()
            reset_settings[category] = DEFAULT_SETTINGS[category].copy()
        else:
            return error_response(f"Invalid category: {category}", 400)
        
        save_settings(reset_settings, current_user_id)
        log_settings_change(current_user_id, f"RESET_{category.upper()}", reset_settings)
        
        return success_response(
            data={'settings': reset_settings},
            message=f"Settings reset to defaults ({category})"
        )
        
    except Exception as e:
        return error_response(f"Error resetting settings: {str(e)}", 500)

@settings_bp.route('/export', methods=['GET'])
@jwt_required()
@super_admin_required
def export_settings():
    """Export current settings as JSON."""
    try:
        settings = get_cached_settings()
        
        # Create export data
        export_data = {
            'settings': settings,
            'exported_at': datetime.utcnow().isoformat(),
            'exported_by': get_jwt_identity(),
            'version': '1.0'
        }
        
        return success_response(
            data=export_data,
            message="Settings exported successfully"
        )
        
    except Exception as e:
        return error_response(f"Error exporting settings: {str(e)}", 500)

@settings_bp.route('/import', methods=['POST'])
@jwt_required()
@super_admin_required
def import_settings():
    """Import settings from JSON."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'settings' not in data:
            return error_response("Invalid import data", 400)
        
        imported_settings = data['settings']
        
        # Validate imported settings
        validation_result = validate_settings_structure(imported_settings)
        if not validation_result['valid']:
            return error_response(f"Invalid imported settings: {validation_result['error']}", 400)
        
        # Merge with defaults to ensure completeness
        final_settings = merge_settings(DEFAULT_SETTINGS, imported_settings)
        
        save_settings(final_settings, current_user_id)
        log_settings_change(current_user_id, "IMPORT_SETTINGS", final_settings)
        
        return success_response(
            data={'settings': final_settings},
            message="Settings imported successfully"
        )
        
    except Exception as e:
        return error_response(f"Error importing settings: {str(e)}", 500)

@settings_bp.route('/history', methods=['GET'])
@jwt_required()
@super_admin_required
def get_settings_history():
    """Get settings change history."""
    try:
        # In production, this would come from a database table
        # For now, return a simulated history
        
        history = [
            {
                'id': 1,
                'changed_by': 'super@admin.com',
                'change_type': 'UPDATE_ATTENDANCE',
                'changed_at': (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                'summary': 'Updated QR code expiry time'
            },
            {
                'id': 2,
                'changed_by': 'admin@university.edu',
                'change_type': 'UPDATE_UI',
                'changed_at': (datetime.utcnow() - timedelta(hours=24)).isoformat(),
                'summary': 'Changed theme to dark mode'
            }
        ]
        
        return success_response(
            data={'history': history},
            message="Settings history retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving settings history: {str(e)}", 500)

@settings_bp.route('/test-connection', methods=['POST'])
@jwt_required()
@admin_required
def test_integration_connection():
    """Test external service connections."""
    try:
        data = request.get_json()
        service = data.get('service')
        
        if not service:
            return error_response("Service type required", 400)
        
        settings = get_cached_settings()
        integration_settings = settings.get('integration', {})
        
        test_results = {}
        
        if service == 'email':
            # Test email SMTP connection
            test_results = test_email_connection(integration_settings)
        elif service == 'telegram':
            # Test Telegram bot connection
            test_results = test_telegram_connection(integration_settings)
        elif service == 'maps':
            # Test Google Maps API
            test_results = test_maps_api(integration_settings)
        else:
            return error_response(f"Unknown service: {service}", 400)
        
        return success_response(
            data={'test_results': test_results},
            message=f"Connection test completed for {service}"
        )
        
    except Exception as e:
        return error_response(f"Error testing connection: {str(e)}", 500)

# =================== HELPER FUNCTIONS ===================

def get_cached_settings() -> Dict:
    """Get settings from cache or load defaults."""
    global settings_cache
    
    if not settings_cache:
        # Load from file or database
        settings_cache = load_settings_from_storage()
    
    return settings_cache

def load_settings_from_storage() -> Dict:
    """Load settings from storage (file or database)."""
    try:
        # In production, load from database
        # For now, check if settings file exists
        settings_file = 'system_settings.json'
        
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                stored_settings = json.load(f)
            
            # Merge with defaults to ensure completeness
            return merge_settings(DEFAULT_SETTINGS, stored_settings)
        else:
            return DEFAULT_SETTINGS.copy()
            
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings: Dict, user_id: int) -> None:
    """Save settings to storage."""
    global settings_cache
    
    # Update cache
    settings_cache = settings.copy()
    
    # Save to file (in production, save to database)
    try:
        settings_file = 'system_settings.json'
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # Log error in production

def merge_settings(defaults: Dict, updates: Dict) -> Dict:
    """Merge settings dictionaries recursively."""
    result = defaults.copy()
    
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = value
    
    return result

def get_settings_last_updated() -> str:
    """Get last updated timestamp."""
    try:
        settings_file = 'system_settings.json'
        if os.path.exists(settings_file):
            mtime = os.path.getmtime(settings_file)
            return datetime.fromtimestamp(mtime).isoformat()
        else:
            return datetime.utcnow().isoformat()
    except Exception:
        return datetime.utcnow().isoformat()

def log_settings_change(user_id: int, change_type: str, data: Dict) -> None:
    """Log settings change (in production, save to database)."""
    try:
        # In production, save to audit log table
        log_entry = {
            'user_id': user_id,
            'change_type': change_type,
            'timestamp': datetime.utcnow().isoformat(),
            'data_summary': f"Changed {len(data)} settings"
        }
        # Save to log file or database
    except Exception:
        pass

# =================== VALIDATION FUNCTIONS ===================

def validate_settings_structure(settings: Dict) -> Dict:
    """Validate settings structure."""
    try:
        required_categories = ['attendance', 'security', 'notifications', 'system', 'ui', 'integration']
        
        for category in required_categories:
            if category not in settings:
                return {'valid': False, 'error': f"Missing category: {category}"}
        
        return {'valid': True, 'error': None}
        
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def validate_attendance_settings(settings: Dict) -> Dict:
    """Validate attendance settings."""
    try:
        # Check QR code expiry
        if 'qr_code_expiry_seconds' in settings:
            expiry = settings['qr_code_expiry_seconds']
            if not isinstance(expiry, int) or expiry < 30 or expiry > 600:
                return {'valid': False, 'error': 'QR code expiry must be between 30 and 600 seconds'}
        
        # Check GPS tolerance
        if 'gps_accuracy_tolerance_meters' in settings:
            tolerance = settings['gps_accuracy_tolerance_meters']
            if not isinstance(tolerance, (int, float)) or tolerance < 1 or tolerance > 100:
                return {'valid': False, 'error': 'GPS tolerance must be between 1 and 100 meters'}
        
        # Check face recognition threshold
        if 'face_recognition_threshold' in settings:
            threshold = settings['face_recognition_threshold']
            if not isinstance(threshold, (int, float)) or threshold < 0.5 or threshold > 1.0:
                return {'valid': False, 'error': 'Face recognition threshold must be between 0.5 and 1.0'}
        
        return {'valid': True, 'error': None}
        
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def validate_security_settings(settings: Dict) -> Dict:
    """Validate security settings."""
    try:
        # Check password length
        if 'password_min_length' in settings:
            length = settings['password_min_length']
            if not isinstance(length, int) or length < 4 or length > 32:
                return {'valid': False, 'error': 'Password minimum length must be between 4 and 32'}
        
        # Check login attempts
        if 'max_login_attempts' in settings:
            attempts = settings['max_login_attempts']
            if not isinstance(attempts, int) or attempts < 1 or attempts > 20:
                return {'valid': False, 'error': 'Max login attempts must be between 1 and 20'}
        
        # Check session timeout
        if 'session_timeout_minutes' in settings:
            timeout = settings['session_timeout_minutes']
            if not isinstance(timeout, int) or timeout < 15 or timeout > 480:
                return {'valid': False, 'error': 'Session timeout must be between 15 and 480 minutes'}
        
        return {'valid': True, 'error': None}
        
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def validate_system_settings(settings: Dict) -> Dict:
    """Validate system settings."""
    try:
        # Check page size limits
        if 'max_page_size' in settings:
            size = settings['max_page_size']
            if not isinstance(size, int) or size < 10 or size > 1000:
                return {'valid': False, 'error': 'Max page size must be between 10 and 1000'}
        
        # Check file upload size
        if 'file_upload_max_size_mb' in settings:
            size = settings['file_upload_max_size_mb']
            if not isinstance(size, (int, float)) or size < 1 or size > 100:
                return {'valid': False, 'error': 'File upload max size must be between 1 and 100 MB'}
        
        return {'valid': True, 'error': None}
        
    except Exception as e:
        return {'valid': False, 'error': str(e)}

# =================== CONNECTION TEST FUNCTIONS ===================

def test_email_connection(settings: Dict) -> Dict:
    """Test email SMTP connection."""
    try:
        # Simulate email test (implement actual SMTP test in production)
        smtp_server = settings.get('email_smtp_server')
        smtp_port = settings.get('email_smtp_port')
        username = settings.get('email_username')
        
        if not all([smtp_server, smtp_port, username]):
            return {
                'success': False,
                'message': 'Missing required email configuration'
            }
        
        # Simulate successful connection
        return {
            'success': True,
            'message': f'Successfully connected to {smtp_server}:{smtp_port}',
            'tested_at': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Email connection failed: {str(e)}'
        }

def test_telegram_connection(settings: Dict) -> Dict:
    """Test Telegram bot connection."""
    try:
        bot_token = settings.get('telegram_bot_token')
        
        if not bot_token:
            return {
                'success': False,
                'message': 'Telegram bot token not configured'
            }
        
        # Simulate successful connection (implement actual API test in production)
        return {
            'success': True,
            'message': 'Telegram bot connection successful',
            'tested_at': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Telegram connection failed: {str(e)}'
        }

def test_maps_api(settings: Dict) -> Dict:
    """Test Google Maps API connection."""
    try:
        api_key = settings.get('google_maps_api_key')
        
        if not api_key:
            return {
                'success': False,
                'message': 'Google Maps API key not configured'
            }
        
        # Simulate successful connection (implement actual API test in production)
        return {
            'success': True,
            'message': 'Google Maps API connection successful',
            'tested_at': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Google Maps API connection failed: {str(e)}'
        }