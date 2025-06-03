# backend/app/api/rooms.py
"""Room Management API - Admin Only."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.room import Room
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required

rooms_bp = Blueprint('rooms', __name__)

@rooms_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Rooms service is running')

@rooms_bp.route('/', methods=['GET'])
@jwt_required()
def get_rooms():
    """Get all rooms."""
    try:
        building = request.args.get('building')
        floor = request.args.get('floor', type=int)
        is_active = request.args.get('is_active', type=bool, default=True)
        
        query = Room.query
        
        if building:
            query = query.filter_by(building=building)
        if floor is not None:
            query = query.filter_by(floor=floor)
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        
        rooms = query.all()
        
        return success_response(
            data=[room.to_dict() for room in rooms]
        )
        
    except Exception as e:
        return error_response(f"Error fetching rooms: {str(e)}", 500)

@rooms_bp.route('/<int:room_id>', methods=['GET'])
@jwt_required()
def get_room(room_id):
    """Get single room details."""
    try:
        room = Room.query.get_or_404(room_id)
        return success_response(data=room.to_dict())
        
    except Exception as e:
        return error_response(f"Error fetching room: {str(e)}", 500)

@rooms_bp.route('/', methods=['POST'])
@jwt_required()
@admin_required
def create_room():
    """Create new room with GPS boundaries."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['name', 'building', 'floor', 'altitude', 'gps_boundaries', 
                   'center_latitude', 'center_longitude']
        for field in required:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Validate GPS boundaries (should have 4 points)
        if len(data['gps_boundaries']) != 4:
            return error_response("GPS boundaries must have exactly 4 points", 400)
        
        # Check if room name already exists
        if Room.query.filter_by(name=data['name']).first():
            return error_response(f"Room {data['name']} already exists", 400)
        
        # Create room
        room = Room(
            name=data['name'],
            building=data['building'],
            floor=data['floor'],
            altitude=data['altitude'],
            gps_boundaries=data['gps_boundaries'],
            center_latitude=data['center_latitude'],
            center_longitude=data['center_longitude'],
            radius_meters=data.get('radius_meters', 5.0),
            capacity=data.get('capacity', 30)
        )
        
        db.session.add(room)
        db.session.commit()
        
        return success_response(
            data=room.to_dict(),
            message="Room created successfully"
        ), 201
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error creating room: {str(e)}", 500)

@rooms_bp.route('/<int:room_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_room(room_id):
    """Update room information."""
    try:
        room = Room.query.get_or_404(room_id)
        data = request.get_json()
        
        # Update allowed fields
        updatable_fields = [
            'name', 'building', 'floor', 'altitude', 'gps_boundaries',
            'center_latitude', 'center_longitude', 'radius_meters',
            'capacity', 'is_active'
        ]
        
        for field in updatable_fields:
            if field in data:
                setattr(room, field, data[field])
        
        db.session.commit()
        
        return success_response(
            data=room.to_dict(),
            message="Room updated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error updating room: {str(e)}", 500)

@rooms_bp.route('/<int:room_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_room(room_id):
    """Delete room (soft delete)."""
    try:
        room = Room.query.get_or_404(room_id)
        
        # Check if room has active schedules
        if room.schedules.filter_by(is_active=True).count() > 0:
            return error_response("Cannot delete room with active schedules", 400)
        
        # Soft delete
        room.is_active = False
        db.session.commit()
        
        return success_response(message="Room deleted successfully")
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error deleting room: {str(e)}", 500)

@rooms_bp.route('/<int:room_id>/check-location', methods=['POST'])
@jwt_required()
def check_location(room_id):
    """Check if GPS location is inside room boundaries."""
    try:
        room = Room.query.get_or_404(room_id)
        data = request.get_json()
        
        if 'latitude' not in data or 'longitude' not in data:
            return error_response("Latitude and longitude required", 400)
        
        # Simple distance check from center
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371000  # Earth radius in meters
        lat1 = radians(room.center_latitude)
        lon1 = radians(room.center_longitude)
        lat2 = radians(data['latitude'])
        lon2 = radians(data['longitude'])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        
        is_inside = distance <= room.radius_meters
        
        return success_response(
            data={
                'is_inside': is_inside,
                'distance_meters': round(distance, 2),
                'room_radius': room.radius_meters
            }
        )
        
    except Exception as e:
        return error_response(f"Error checking location: {str(e)}", 500)

