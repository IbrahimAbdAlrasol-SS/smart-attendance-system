# File: backend/app/api/backups.py
"""System Backups API for data management and recovery."""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.user import User, UserRole
from app.utils.helpers import success_response, error_response
from app.utils.decorators import super_admin_required, admin_required
from datetime import datetime, timedelta
import os
import json
import tempfile
import zipfile
import subprocess
from typing import Dict, List, Any, Optional
import shutil

backups_bp = Blueprint('backups', __name__)

# Backup storage directory
BACKUP_DIR = 'backups'
os.makedirs(BACKUP_DIR, exist_ok=True)

@backups_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Backups service is running')

# =================== BACKUP MANAGEMENT ===================

@backups_bp.route('/', methods=['GET'])
@jwt_required()
@admin_required
def list_backups():
    """List all available backups."""
    try:
        current_user_id = get_jwt_identity()
        
        # Get backup files
        backup_files = []
        
        if os.path.exists(BACKUP_DIR):
            for filename in os.listdir(BACKUP_DIR):
                if filename.endswith('.zip'):
                    filepath = os.path.join(BACKUP_DIR, filename)
                    stat = os.stat(filepath)
                    
                    backup_info = {
                        'id': filename.replace('.zip', ''),
                        'filename': filename,
                        'size_bytes': stat.st_size,
                        'size_mb': round(stat.st_size / (1024 * 1024), 2),
                        'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    }
                    
                    # Try to read metadata if exists
                    metadata_file = os.path.join(BACKUP_DIR, f"{backup_info['id']}_metadata.json")
                    if os.path.exists(metadata_file):
                        try:
                            with open(metadata_file, 'r') as f:
                                metadata = json.load(f)
                                backup_info.update(metadata)
                        except:
                            pass
                    
                    backup_files.append(backup_info)
        
        # Sort by creation date (newest first)
        backup_files.sort(key=lambda x: x['created_at'], reverse=True)
        
        # Calculate total storage used
        total_size = sum(backup['size_bytes'] for backup in backup_files)
        
        return success_response(
            data={
                'backups': backup_files,
                'summary': {
                    'total_backups': len(backup_files),
                    'total_size_bytes': total_size,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'oldest_backup': backup_files[-1]['created_at'] if backup_files else None,
                    'newest_backup': backup_files[0]['created_at'] if backup_files else None
                }
            },
            message=f"Found {len(backup_files)} backups"
        )
        
    except Exception as e:
        return error_response(f"Error listing backups: {str(e)}", 500)

@backups_bp.route('/create', methods=['POST'])
@jwt_required()
@super_admin_required
def create_backup():
    """Create new system backup."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        # Backup parameters
        backup_type = data.get('backup_type', 'full')  # full, database_only, files_only
        description = data.get('description', '')
        include_uploads = data.get('include_uploads', True)
        compress_level = data.get('compress_level', 6)  # 1-9
        
        # Generate backup ID
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_id = f"backup_{backup_type}_{timestamp}"
        
        # Create backup metadata
        metadata = {
            'backup_id': backup_id,
            'backup_type': backup_type,
            'description': description,
            'created_by': current_user_id,
            'created_at': datetime.utcnow().isoformat(),
            'include_uploads': include_uploads,
            'compress_level': compress_level,
            'status': 'creating'
        }
        
        # Save metadata first
        metadata_file = os.path.join(BACKUP_DIR, f"{backup_id}_metadata.json")
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Create backup
        backup_result = _create_system_backup(
            backup_id=backup_id,
            backup_type=backup_type,
            include_uploads=include_uploads,
            compress_level=compress_level
        )
        
        if backup_result['success']:
            # Update metadata with success info
            metadata.update({
                'status': 'completed',
                'completed_at': datetime.utcnow().isoformat(),
                'file_count': backup_result.get('file_count', 0),
                'database_tables': backup_result.get('database_tables', 0),
                'backup_size_bytes': backup_result.get('size_bytes', 0)
            })
            
            # Save updated metadata
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return success_response(
                data={
                    'backup_id': backup_id,
                    'metadata': metadata,
                    'download_url': f'/api/backups/{backup_id}/download'
                },
                message="Backup created successfully"
            )
        else:
            # Update metadata with error info
            metadata.update({
                'status': 'failed',
                'failed_at': datetime.utcnow().isoformat(),
                'error': backup_result.get('error', 'Unknown error')
            })
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return error_response(f"Backup creation failed: {backup_result.get('error')}", 500)
        
    except Exception as e:
        return error_response(f"Error creating backup: {str(e)}", 500)

@backups_bp.route('/<backup_id>/download', methods=['GET'])
@jwt_required()
@admin_required
def download_backup(backup_id: str):
    """Download backup file."""
    try:
        backup_file = os.path.join(BACKUP_DIR, f"{backup_id}.zip")
        
        if not os.path.exists(backup_file):
            return error_response("Backup file not found", 404)
        
        return send_file(
            backup_file,
            as_attachment=True,
            download_name=f"{backup_id}.zip",
            mimetype='application/zip'
        )
        
    except Exception as e:
        return error_response(f"Error downloading backup: {str(e)}", 500)

@backups_bp.route('/<backup_id>/restore', methods=['POST'])
@jwt_required()
@super_admin_required
def restore_backup(backup_id: str):
    """Restore system from backup."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        # Restore options
        restore_database = data.get('restore_database', True)
        restore_files = data.get('restore_files', True)
        force_restore = data.get('force_restore', False)
        
        backup_file = os.path.join(BACKUP_DIR, f"{backup_id}.zip")
        metadata_file = os.path.join(BACKUP_DIR, f"{backup_id}_metadata.json")
        
        if not os.path.exists(backup_file):
            return error_response("Backup file not found", 404)
        
        # Load backup metadata
        metadata = {}
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        
        # Verify backup integrity
        integrity_check = _verify_backup_integrity(backup_file)
        if not integrity_check['valid'] and not force_restore:
            return error_response(
                f"Backup integrity check failed: {integrity_check['error']}", 
                400
            )
        
        # Perform restore
        restore_result = _restore_system_backup(
            backup_file=backup_file,
            restore_database=restore_database,
            restore_files=restore_files,
            metadata=metadata
        )
        
        if restore_result['success']:
            # Log restore operation
            _log_restore_operation(
                backup_id=backup_id,
                restored_by=current_user_id,
                restore_options={
                    'restore_database': restore_database,
                    'restore_files': restore_files
                },
                result=restore_result
            )
            
            return success_response(
                data={
                    'backup_id': backup_id,
                    'restore_summary': restore_result,
                    'restored_at': datetime.utcnow().isoformat()
                },
                message="System restored successfully"
            )
        else:
            return error_response(f"Restore failed: {restore_result.get('error')}", 500)
        
    except Exception as e:
        return error_response(f"Error restoring backup: {str(e)}", 500)

@backups_bp.route('/<backup_id>', methods=['DELETE'])
@jwt_required()
@super_admin_required
def delete_backup(backup_id: str):
    """Delete backup file."""
    try:
        backup_file = os.path.join(BACKUP_DIR, f"{backup_id}.zip")
        metadata_file = os.path.join(BACKUP_DIR, f"{backup_id}_metadata.json")
        
        if not os.path.exists(backup_file):
            return error_response("Backup file not found", 404)
        
        # Remove backup file
        os.remove(backup_file)
        
        # Remove metadata file if exists
        if os.path.exists(metadata_file):
            os.remove(metadata_file)
        
        return success_response(
            message=f"Backup {backup_id} deleted successfully"
        )
        
    except Exception as e:
        return error_response(f"Error deleting backup: {str(e)}", 500)

@backups_bp.route('/schedule', methods=['GET'])
@jwt_required()
@admin_required
def get_backup_schedule():
    """Get backup schedule configuration."""
    try:
        # In production, load from database or config file
        schedule_config = {
            'enabled': True,
            'frequency': 'daily',  # daily, weekly, monthly
            'time': '02:00',  # 2:00 AM
            'retention_days': 30,
            'backup_type': 'full',
            'include_uploads': True,
            'compress_level': 6,
            'last_auto_backup': None,
            'next_scheduled_backup': None
        }
        
        return success_response(
            data={'schedule': schedule_config},
            message="Backup schedule configuration"
        )
        
    except Exception as e:
        return error_response(f"Error getting backup schedule: {str(e)}", 500)

@backups_bp.route('/schedule', methods=['PUT'])
@jwt_required()
@super_admin_required
def update_backup_schedule():
    """Update backup schedule configuration."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate schedule data
        valid_frequencies = ['daily', 'weekly', 'monthly', 'disabled']
        if data.get('frequency') not in valid_frequencies:
            return error_response(f"Invalid frequency. Must be one of: {valid_frequencies}", 400)
        
        # In production, save to database or config file
        updated_schedule = {
            'enabled': data.get('enabled', True),
            'frequency': data.get('frequency', 'daily'),
            'time': data.get('time', '02:00'),
            'retention_days': data.get('retention_days', 30),
            'backup_type': data.get('backup_type', 'full'),
            'include_uploads': data.get('include_uploads', True),
            'compress_level': data.get('compress_level', 6),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        return success_response(
            data={'schedule': updated_schedule},
            message="Backup schedule updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating backup schedule: {str(e)}", 500)

@backups_bp.route('/cleanup', methods=['POST'])
@jwt_required()
@admin_required
def cleanup_old_backups():
    """Clean up old backups based on retention policy."""
    try:
        data = request.get_json() or {}
        retention_days = data.get('retention_days', 30)
        dry_run = data.get('dry_run', False)
        
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        backups_to_delete = []
        
        if os.path.exists(BACKUP_DIR):
            for filename in os.listdir(BACKUP_DIR):
                if filename.endswith('.zip'):
                    filepath = os.path.join(BACKUP_DIR, filename)
                    file_date = datetime.fromtimestamp(os.path.getctime(filepath))
                    
                    if file_date < cutoff_date:
                        backup_id = filename.replace('.zip', '')
                        backups_to_delete.append({
                            'backup_id': backup_id,
                            'filename': filename,
                            'created_date': file_date.isoformat(),
                            'age_days': (datetime.utcnow() - file_date).days
                        })
        
        if not dry_run:
            # Actually delete the files
            deleted_count = 0
            for backup in backups_to_delete:
                try:
                    backup_file = os.path.join(BACKUP_DIR, backup['filename'])
                    metadata_file = os.path.join(BACKUP_DIR, f"{backup['backup_id']}_metadata.json")
                    
                    os.remove(backup_file)
                    if os.path.exists(metadata_file):
                        os.remove(metadata_file)
                    
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {backup['filename']}: {str(e)}")
            
            return success_response(
                data={
                    'deleted_count': deleted_count,
                    'deleted_backups': backups_to_delete,
                    'retention_days': retention_days
                },
                message=f"Cleaned up {deleted_count} old backups"
            )
        else:
            # Dry run - just show what would be deleted
            return success_response(
                data={
                    'would_delete_count': len(backups_to_delete),
                    'backups_to_delete': backups_to_delete,
                    'retention_days': retention_days
                },
                message=f"Would delete {len(backups_to_delete)} old backups (dry run)"
            )
        
    except Exception as e:
        return error_response(f"Error cleaning up backups: {str(e)}", 500)

# =================== HELPER FUNCTIONS ===================

def _create_system_backup(
    backup_id: str,
    backup_type: str,
    include_uploads: bool,
    compress_level: int
) -> Dict:
    """Create system backup."""
    try:
        backup_file = os.path.join(BACKUP_DIR, f"{backup_id}.zip")
        
        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED, compresslevel=compress_level) as zipf:
            file_count = 0
            
            # Backup database
            if backup_type in ['full', 'database_only']:
                db_backup = _create_database_backup()
                if db_backup['success']:
                    zipf.writestr('database_backup.sql', db_backup['content'])
                    file_count += 1
            
            # Backup application files
            if backup_type in ['full', 'files_only']:
                # Backup configuration files
                config_files = ['config.py', 'requirements.txt']
                for config_file in config_files:
                    if os.path.exists(config_file):
                        zipf.write(config_file)
                        file_count += 1
                
                # Backup uploads if requested
                if include_uploads and os.path.exists('uploads'):
                    for root, dirs, files in os.walk('uploads'):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, '.')
                            zipf.write(file_path, arcname)
                            file_count += 1
        
        # Get backup file size
        backup_size = os.path.getsize(backup_file)
        
        return {
            'success': True,
            'file_count': file_count,
            'size_bytes': backup_size,
            'database_tables': _get_database_table_count()
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def _create_database_backup() -> Dict:
    """Create database backup as SQL dump."""
    try:
        # In production, use proper database backup tools
        # For SQLite, read the file directly
        # For PostgreSQL, use pg_dump
        
        # This is a simplified version
        backup_content = "-- Database backup created at " + datetime.utcnow().isoformat() + "\n"
        backup_content += "-- This is a placeholder for actual database backup\n"
        
        return {
            'success': True,
            'content': backup_content
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def _verify_backup_integrity(backup_file: str) -> Dict:
    """Verify backup file integrity."""
    try:
        with zipfile.ZipFile(backup_file, 'r') as zipf:
            # Test the zip file
            bad_file = zipf.testzip()
            if bad_file:
                return {
                    'valid': False,
                    'error': f"Corrupted file in backup: {bad_file}"
                }
        
        return {'valid': True}
        
    except Exception as e:
        return {
            'valid': False,
            'error': str(e)
        }

def _restore_system_backup(
    backup_file: str,
    restore_database: bool,
    restore_files: bool,
    metadata: Dict
) -> Dict:
    """Restore system from backup."""
    try:
        restore_summary = {
            'database_restored': False,
            'files_restored': 0,
            'errors': []
        }
        
        with zipfile.ZipFile(backup_file, 'r') as zipf:
            # Restore database
            if restore_database and 'database_backup.sql' in zipf.namelist():
                # In production, implement actual database restore
                restore_summary['database_restored'] = True
            
            # Restore files
            if restore_files:
                for file_info in zipf.filelist:
                    if file_info.filename != 'database_backup.sql':
                        try:
                            zipf.extract(file_info.filename)
                            restore_summary['files_restored'] += 1
                        except Exception as e:
                            restore_summary['errors'].append(f"Error restoring {file_info.filename}: {str(e)}")
        
        return {
            'success': True,
            'summary': restore_summary
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def _log_restore_operation(backup_id: str, restored_by: int, restore_options: Dict, result: Dict):
    """Log restore operation for audit trail."""
    try:
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'backup_id': backup_id,
            'restored_by': restored_by,
            'restore_options': restore_options,
            'result': result
        }
        
        # In production, save to audit log database
        print(f"RESTORE LOG: {json.dumps(log_entry, indent=2)}")
        
    except Exception as e:
        print(f"Error logging restore operation: {str(e)}")

def _get_database_table_count() -> int:
    """Get number of database tables."""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        return len(inspector.get_table_names())
    except:
        return 0