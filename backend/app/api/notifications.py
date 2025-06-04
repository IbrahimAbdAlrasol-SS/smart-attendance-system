# File: backend/app/api/notifications.py
"""Comprehensive Notifications API for system-wide messaging."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.user import User, UserRole
from app.models.student import Student, Section, StudyType
from app.models.lecture import Lecture
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, teacher_required
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, desc
from typing import Dict, List, Any, Optional
import json
from enum import Enum

notifications_bp = Blueprint('notifications', __name__)

# Notification Types
class NotificationType(Enum):
    INFO = 'info'
    WARNING = 'warning'
    SUCCESS = 'success'
    ERROR = 'error'
    URGENT = 'urgent'

# Notification Priority
class NotificationPriority(Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    URGENT = 'urgent'

# In-memory notification storage (in production, use database table)
notifications_store = []
notification_id_counter = 1

@notifications_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Notifications service is running')

# =================== NOTIFICATION MANAGEMENT ===================

@notifications_bp.route('/', methods=['GET'])
@jwt_required()
def get_notifications():
    """Get user's notifications with filters."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        unread_only = request.args.get('unread_only', type=bool, default=False)
        notification_type = request.args.get('type')
        priority = request.args.get('priority')
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Filter notifications for current user
        user_notifications = []
        for notification in notifications_store:
            # Check if notification is for this user
            if is_notification_for_user(notification, current_user_id, user):
                # Apply filters
                if unread_only and notification.get('read_at'):
                    continue
                
                if notification_type and notification.get('type') != notification_type:
                    continue
                
                if priority and notification.get('priority') != priority:
                    continue
                
                if from_date:
                    try:
                        filter_date = datetime.fromisoformat(from_date)
                        notif_date = datetime.fromisoformat(notification['created_at'])
                        if notif_date < filter_date:
                            continue
                    except ValueError:
                        pass
                
                if to_date:
                    try:
                        filter_date = datetime.fromisoformat(to_date)
                        notif_date = datetime.fromisoformat(notification['created_at'])
                        if notif_date > filter_date:
                            continue
                    except ValueError:
                        pass
                
                user_notifications.append(notification)
        
        # Sort by creation date (newest first)
        user_notifications.sort(key=lambda x: x['created_at'], reverse=True)
        
        # Paginate
        total = len(user_notifications)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_notifications = user_notifications[start:end]
        
        # Count unread
        unread_count = len([n for n in user_notifications if not n.get('read_at')])
        
        return success_response(
            data={
                'notifications': paginated_notifications,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page,
                    'has_next': end < total,
                    'has_prev': page > 1
                },
                'summary': {
                    'total_notifications': total,
                    'unread_count': unread_count
                }
            },
            message=f"Found {len(paginated_notifications)} notifications"
        )
        
    except Exception as e:
        return error_response(f"Error fetching notifications: {str(e)}", 500)

@notifications_bp.route('/', methods=['POST'])
@jwt_required()
@admin_required
def create_notification():
    """Create and send notification."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate required fields
        required_fields = ['title', 'message', 'recipients']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Create notification
        notification = create_notification_object(
            title=data['title'],
            message=data['message'],
            notification_type=data.get('type', NotificationType.INFO.value),
            priority=data.get('priority', NotificationPriority.MEDIUM.value),
            recipients=data['recipients'],
            sender_id=current_user_id,
            action_url=data.get('action_url'),
            expiry_date=data.get('expiry_date'),
            category=data.get('category', 'general'),
            metadata=data.get('metadata', {})
        )
        
        # Send notification
        send_result = send_notification(notification)
        
        return success_response(
            data={
                'notification': notification,
                'send_result': send_result
            },
            message="Notification created and sent successfully"
        ), 201
        
    except Exception as e:
        return error_response(f"Error creating notification: {str(e)}", 500)

@notifications_bp.route('/<int:notification_id>/read', methods=['PUT'])
@jwt_required()
def mark_as_read(notification_id):
    """Mark notification as read."""
    try:
        current_user_id = get_jwt_identity()
        
        # Find notification
        notification = find_notification_by_id(notification_id)
        if not notification:
            return error_response("Notification not found", 404)
        
        # Check if user can access this notification
        user = User.query.get(current_user_id)
        if not is_notification_for_user(notification, current_user_id, user):
            return error_response("Notification not accessible", 403)
        
        # Mark as read
        if 'read_by' not in notification:
            notification['read_by'] = {}
        
        notification['read_by'][str(current_user_id)] = datetime.utcnow().isoformat()
        notification['read_at'] = datetime.utcnow().isoformat()
        
        return success_response(
            data={'notification': notification},
            message="Notification marked as read"
        )
        
    except Exception as e:
        return error_response(f"Error marking notification as read: {str(e)}", 500)

@notifications_bp.route('/<int:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    """Delete notification (soft delete or admin delete)."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Find notification
        notification = find_notification_by_id(notification_id)
        if not notification:
            return error_response("Notification not found", 404)
        
        # Check permissions
        if user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # Admin can delete any notification
            remove_notification_from_store(notification_id)
            message = "Notification deleted permanently"
        else:
            # User can only hide notification for themselves
            if 'hidden_by' not in notification:
                notification['hidden_by'] = {}
            notification['hidden_by'][str(current_user_id)] = datetime.utcnow().isoformat()
            message = "Notification hidden"
        
        return success_response(message=message)
        
    except Exception as e:
        return error_response(f"Error deleting notification: {str(e)}", 500)

@notifications_bp.route('/bulk', methods=['POST'])
@jwt_required()
@admin_required
def send_bulk_notification():
    """Send notification to multiple users or groups."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate required fields
        required_fields = ['title', 'message', 'target_type']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        target_type = data['target_type']
        recipients = []
        
        # Determine recipients based on target type
        if target_type == 'all_users':
            recipients = ['all_users']
        elif target_type == 'all_students':
            recipients = ['all_students']
        elif target_type == 'all_teachers':
            recipients = ['all_teachers']
        elif target_type == 'section':
            section = data.get('section')
            if not section:
                return error_response("Section required for section target", 400)
            recipients = [f'section_{section}']
        elif target_type == 'study_year':
            study_year = data.get('study_year')
            if not study_year:
                return error_response("Study year required for study year target", 400)
            recipients = [f'study_year_{study_year}']
        elif target_type == 'specific_users':
            user_ids = data.get('user_ids', [])
            if not user_ids:
                return error_response("User IDs required for specific users target", 400)
            recipients = [f'user_{uid}' for uid in user_ids]
        else:
            return error_response(f"Invalid target type: {target_type}", 400)
        
        # Create and send notification
        notification = create_notification_object(
            title=data['title'],
            message=data['message'],
            notification_type=data.get('type', NotificationType.INFO.value),
            priority=data.get('priority', NotificationPriority.MEDIUM.value),
            recipients=recipients,
            sender_id=current_user_id,
            action_url=data.get('action_url'),
            expiry_date=data.get('expiry_date'),
            category=data.get('category', 'bulk'),
            metadata=data.get('metadata', {})
        )
        
        # Calculate recipient count
        recipient_count = calculate_recipient_count(recipients)
        
        send_result = send_notification(notification)
        
        return success_response(
            data={
                'notification': notification,
                'recipient_count': recipient_count,
                'send_result': send_result
            },
            message=f"Bulk notification sent to {recipient_count} recipients"
        )
        
    except Exception as e:
        return error_response(f"Error sending bulk notification: {str(e)}", 500)

@notifications_bp.route('/unread', methods=['GET'])
@jwt_required()
def get_unread_notifications():
    """Get only unread notifications for current user."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Filter unread notifications
        unread_notifications = []
        for notification in notifications_store:
            if is_notification_for_user(notification, current_user_id, user):
                if not notification.get('read_by', {}).get(str(current_user_id)):
                    unread_notifications.append(notification)
        
        # Sort by priority and date
        unread_notifications.sort(key=lambda x: (
            priority_sort_key(x.get('priority', 'medium')),
            x['created_at']
        ), reverse=True)
        
        # Categorize by priority
        urgent_count = len([n for n in unread_notifications if n.get('priority') == 'urgent'])
        high_count = len([n for n in unread_notifications if n.get('priority') == 'high'])
        
        return success_response(
            data={
                'notifications': unread_notifications,
                'summary': {
                    'total_unread': len(unread_notifications),
                    'urgent_count': urgent_count,
                    'high_priority_count': high_count
                }
            },
            message=f"Found {len(unread_notifications)} unread notifications"
        )
        
    except Exception as e:
        return error_response(f"Error fetching unread notifications: {str(e)}", 500)

@notifications_bp.route('/mark-all-read', methods=['PUT'])
@jwt_required()
def mark_all_as_read():
    """Mark all notifications as read for current user."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        marked_count = 0
        
        for notification in notifications_store:
            if is_notification_for_user(notification, current_user_id, user):
                if not notification.get('read_by', {}).get(str(current_user_id)):
                    if 'read_by' not in notification:
                        notification['read_by'] = {}
                    notification['read_by'][str(current_user_id)] = datetime.utcnow().isoformat()
                    marked_count += 1
        
        return success_response(
            data={'marked_count': marked_count},
            message=f"Marked {marked_count} notifications as read"
        )
        
    except Exception as e:
        return error_response(f"Error marking all notifications as read: {str(e)}", 500)

# =================== NOTIFICATION TEMPLATES ===================

@notifications_bp.route('/templates', methods=['GET'])
@jwt_required()
@admin_required
def get_notification_templates():
    """Get notification templates."""
    try:
        templates = [
            {
                'id': 'lecture_reminder',
                'name': 'Lecture Reminder',
                'title': 'محاضرة وشيكة',
                'message': 'لديك محاضرة {lecture_title} في {room} خلال {minutes} دقيقة',
                'type': 'info',
                'priority': 'medium',
                'category': 'academic'
            },
            {
                'id': 'attendance_warning',
                'name': 'Attendance Warning',
                'title': 'تحذير الحضور',
                'message': 'نسبة حضورك في مادة {subject} منخفضة ({attendance_rate}%)',
                'type': 'warning',
                'priority': 'high',
                'category': 'attendance'
            },
            {
                'id': 'system_maintenance',
                'name': 'System Maintenance',
                'title': 'صيانة النظام',
                'message': 'سيكون النظام تحت الصيانة من {start_time} إلى {end_time}',
                'type': 'warning',
                'priority': 'high',
                'category': 'system'
            },
            {
                'id': 'grade_published',
                'name': 'Grades Published',
                'title': 'نشر الدرجات',
                'message': 'تم نشر درجات {exam_name}. يمكنك مراجعة النتائج الآن',
                'type': 'success',
                'priority': 'medium',
                'category': 'academic'
            },
            {
                'id': 'emergency_alert',
                'name': 'Emergency Alert',
                'title': 'تنبيه طارئ',
                'message': 'تنبيه عاجل: {emergency_message}',
                'type': 'urgent',
                'priority': 'urgent',
                'category': 'emergency'
            }
        ]
        
        return success_response(
            data={'templates': templates},
            message="Notification templates retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error fetching templates: {str(e)}", 500)

@notifications_bp.route('/send-template', methods=['POST'])
@jwt_required()
@admin_required
def send_template_notification():
    """Send notification using a template."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        template_id = data.get('template_id')
        template_data = data.get('template_data', {})
        recipients = data.get('recipients', [])
        
        if not template_id:
            return error_response("Template ID required", 400)
        
        if not recipients:
            return error_response("Recipients required", 400)
        
        # Get template
        template = get_notification_template(template_id)
        if not template:
            return error_response("Template not found", 404)
        
        # Replace placeholders in template
        title = template['title']
        message = template['message']
        
        for key, value in template_data.items():
            placeholder = f'{{{key}}}'
            title = title.replace(placeholder, str(value))
            message = message.replace(placeholder, str(value))
        
        # Create and send notification
        notification = create_notification_object(
            title=title,
            message=message,
            notification_type=template['type'],
            priority=template['priority'],
            recipients=recipients,
            sender_id=current_user_id,
            category=template['category'],
            metadata={'template_id': template_id, 'template_data': template_data}
        )
        
        send_result = send_notification(notification)
        
        return success_response(
            data={
                'notification': notification,
                'send_result': send_result
            },
            message="Template notification sent successfully"
        )
        
    except Exception as e:
        return error_response(f"Error sending template notification: {str(e)}", 500)

# =================== NOTIFICATION SETTINGS ===================

@notifications_bp.route('/settings', methods=['GET'])
@jwt_required()
def get_notification_settings():
    """Get user's notification preferences."""
    try:
        current_user_id = get_jwt_identity()
        
        # In production, load from user preferences table
        # For now, return default settings
        settings = {
            'email_notifications': True,
            'push_notifications': True,
            'sms_notifications': False,
            'notification_categories': {
                'academic': True,
                'attendance': True,
                'system': True,
                'emergency': True,
                'general': True
            },
            'priority_filters': {
                'urgent': True,
                'high': True,
                'medium': True,
                'low': False
            },
            'quiet_hours': {
                'enabled': False,
                'start_time': '22:00',
                'end_time': '07:00'
            },
            'digest_frequency': 'daily'  # none, daily, weekly
        }
        
        return success_response(
            data={'settings': settings},
            message="Notification settings retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error fetching notification settings: {str(e)}", 500)

@notifications_bp.route('/settings', methods=['PUT'])
@jwt_required()
def update_notification_settings():
    """Update user's notification preferences."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # In production, save to user preferences table
        # For now, just return the updated settings
        
        return success_response(
            data={'settings': data},
            message="Notification settings updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating notification settings: {str(e)}", 500)

# =================== NOTIFICATION STATISTICS ===================

@notifications_bp.route('/statistics', methods=['GET'])
@jwt_required()
@admin_required
def get_notification_statistics():
    """Get notification system statistics."""
    try:
        # Calculate statistics
        total_notifications = len(notifications_store)
        
        # By type
        type_stats = {}
        for notification in notifications_store:
            notif_type = notification.get('type', 'info')
            type_stats[notif_type] = type_stats.get(notif_type, 0) + 1
        
        # By priority
        priority_stats = {}
        for notification in notifications_store:
            priority = notification.get('priority', 'medium')
            priority_stats[priority] = priority_stats.get(priority, 0) + 1
        
        # Recent activity (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_notifications = [
            n for n in notifications_store 
            if datetime.fromisoformat(n['created_at']) >= seven_days_ago
        ]
        
        # Read rates
        total_with_reads = 0
        total_reads = 0
        
        for notification in notifications_store:
            read_by = notification.get('read_by', {})
            if read_by:
                total_with_reads += 1
                total_reads += len(read_by)
        
        read_rate = (total_reads / (total_notifications * 10)) * 100 if total_notifications > 0 else 0  # Assuming 10 avg recipients
        
        # Daily breakdown (last 7 days)
        daily_stats = []
        for i in range(6, -1, -1):
            day = (datetime.utcnow() - timedelta(days=i)).date()
            day_notifications = [
                n for n in notifications_store 
                if datetime.fromisoformat(n['created_at']).date() == day
            ]
            
            daily_stats.append({
                'date': day.isoformat(),
                'count': len(day_notifications),
                'urgent_count': len([n for n in day_notifications if n.get('priority') == 'urgent'])
            })
        
        return success_response(
            data={
                'overview': {
                    'total_notifications': total_notifications,
                    'recent_notifications_7_days': len(recent_notifications),
                    'estimated_read_rate': round(read_rate, 2)
                },
                'breakdown': {
                    'by_type': type_stats,
                    'by_priority': priority_stats
                },
                'daily_activity': daily_stats,
                'performance': {
                    'notifications_with_reads': total_with_reads,
                    'total_read_actions': total_reads,
                    'avg_reads_per_notification': round(total_reads / total_with_reads, 2) if total_with_reads > 0 else 0
                }
            },
            message="Notification statistics retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error fetching notification statistics: {str(e)}", 500)

@notifications_bp.route('/cleanup', methods=['POST'])
@jwt_required()
@admin_required
def cleanup_old_notifications():
    """Clean up old notifications."""
    try:
        data = request.get_json() or {}
        days_old = data.get('days_old', 30)
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Remove old notifications
        global notifications_store
        original_count = len(notifications_store)
        
        notifications_store = [
            n for n in notifications_store 
            if datetime.fromisoformat(n['created_at']) >= cutoff_date
        ]
        
        removed_count = original_count - len(notifications_store)
        
        return success_response(
            data={
                'removed_count': removed_count,
                'remaining_count': len(notifications_store),
                'cutoff_date': cutoff_date.isoformat()
            },
            message=f"Cleaned up {removed_count} old notifications"
        )
        
    except Exception as e:
        return error_response(f"Error cleaning up notifications: {str(e)}", 500)

# =================== HELPER FUNCTIONS ===================

def create_notification_object(title: str, message: str, notification_type: str, 
                             priority: str, recipients: List[str], sender_id: int,
                             action_url: str = None, expiry_date: str = None,
                             category: str = 'general', metadata: Dict = None) -> Dict:
    """Create notification object."""
    global notification_id_counter
    
    notification = {
        'id': notification_id_counter,
        'title': title,
        'message': message,
        'type': notification_type,
        'priority': priority,
        'recipients': recipients,
        'sender_id': sender_id,
        'action_url': action_url,
        'expiry_date': expiry_date,
        'category': category,
        'metadata': metadata or {},
        'created_at': datetime.utcnow().isoformat(),
        'read_by': {},
        'hidden_by': {}
    }
    
    notification_id_counter += 1
    notifications_store.append(notification)
    
    return notification

def send_notification(notification: Dict) -> Dict:
    """Send notification via various channels."""
    try:
        # In production, implement actual sending logic
        # - Email notifications
        # - Push notifications
        # - SMS notifications
        # - Telegram notifications
        
        recipient_count = calculate_recipient_count(notification['recipients'])
        
        return {
            'success': True,
            'recipient_count': recipient_count,
            'channels': ['in_app'],  # In production: ['email', 'push', 'in_app']
            'sent_at': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'sent_at': datetime.utcnow().isoformat()
        }

def is_notification_for_user(notification: Dict, user_id: int, user: User) -> bool:
    """Check if notification is intended for specific user."""
    recipients = notification.get('recipients', [])
    
    for recipient in recipients:
        if recipient == 'all_users':
            return True
        elif recipient == 'all_students' and user.role == UserRole.STUDENT:
            return True
        elif recipient == 'all_teachers' and user.is_teacher():
            return True
        elif recipient.startswith('user_') and recipient == f'user_{user_id}':
            return True
        elif recipient.startswith('section_') and user.role == UserRole.STUDENT:
            section_name = recipient.replace('section_', '')
            if hasattr(user, 'student_profile') and user.student_profile:
                if user.student_profile.section and user.student_profile.section.value == section_name:
                    return True
        elif recipient.startswith('study_year_') and user.role == UserRole.STUDENT:
            year = int(recipient.replace('study_year_', ''))
            if hasattr(user, 'student_profile') and user.student_profile:
                if user.student_profile.study_year == year:
                    return True
    
    return False

def calculate_recipient_count(recipients: List[str]) -> int:
    """Calculate approximate number of recipients."""
    total = 0
    
    for recipient in recipients:
        if recipient == 'all_users':
            total += User.query.filter_by(is_active=True).count()
        elif recipient == 'all_students':
            total += User.query.filter_by(role=UserRole.STUDENT, is_active=True).count()
        elif recipient == 'all_teachers':
            total += User.query.filter(
                User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR]),
                User.is_active == True
            ).count()
        elif recipient.startswith('user_'):
            total += 1
        elif recipient.startswith('section_'):
            section_name = recipient.replace('section_', '')
            try:
                section_enum = Section[section_name.upper()]
                total += Student.query.filter_by(section=section_enum).count()
            except KeyError:
                pass
        elif recipient.startswith('study_year_'):
            year = int(recipient.replace('study_year_', ''))
            total += Student.query.filter_by(study_year=year).count()
    
    return total

def find_notification_by_id(notification_id: int) -> Optional[Dict]:
    """Find notification by ID."""
    for notification in notifications_store:
        if notification['id'] == notification_id:
            return notification
    return None

def remove_notification_from_store(notification_id: int) -> bool:
    """Remove notification from store."""
    global notifications_store
    original_length = len(notifications_store)
    notifications_store = [n for n in notifications_store if n['id'] != notification_id]
    return len(notifications_store) < original_length

def get_notification_template(template_id: str) -> Optional[Dict]:
    """Get notification template by ID."""
    templates = {
        'lecture_reminder': {
            'id': 'lecture_reminder',
            'title': 'محاضرة وشيكة',
            'message': 'لديك محاضرة {lecture_title} في {room} خلال {minutes} دقيقة',
            'type': 'info',
            'priority': 'medium',
            'category': 'academic'
        },
        'attendance_warning': {
            'id': 'attendance_warning',
            'title': 'تحذير الحضور',
            'message': 'نسبة حضورك في مادة {subject} منخفضة ({attendance_rate}%)',
            'type': 'warning',
            'priority': 'high',
            'category': 'attendance'
        },
        'system_maintenance': {
            'id': 'system_maintenance',
            'title': 'صيانة النظام',
            'message': 'سيكون النظام تحت الصيانة من {start_time} إلى {end_time}',
            'type': 'warning',
            'priority': 'high',
            'category': 'system'
        },
        'grade_published': {
            'id': 'grade_published',
            'title': 'نشر الدرجات',
            'message': 'تم نشر درجات {exam_name}. يمكنك مراجعة النتائج الآن',
            'type': 'success',
            'priority': 'medium',
            'category': 'academic'
        },
        'emergency_alert': {
            'id': 'emergency_alert',
            'title': 'تنبيه طارئ',
            'message': 'تنبيه عاجل: {emergency_message}',
            'type': 'urgent',
            'priority': 'urgent',
            'category': 'emergency'
        }
    }
    
    return templates.get(template_id)

def priority_sort_key(priority: str) -> int:
    """Get sort key for priority."""
    priority_order = {'urgent': 4, 'high': 3, 'medium': 2, 'low': 1}
    return priority_order.get(priority, 2)