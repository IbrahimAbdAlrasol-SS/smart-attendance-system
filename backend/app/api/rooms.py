# File: backend/app/api/rooms.py
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
    """Create new room with 3D GPS boundaries."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['name', 'building', 'floor', 'floor_altitude', 'ceiling_height',
                   'gps_boundaries', 'center_latitude', 'center_longitude']
        for field in required:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Validate GPS boundaries (should have at least 3 points)
        if len(data['gps_boundaries']) < 3:
            return error_response("GPS boundaries must have at least 3 points", 400)
        
        # Check if room name already exists
        if Room.query.filter_by(name=data['name']).first():
            return error_response(f"Room {data['name']} already exists", 400)
        
        # Create room
        room = Room(
            name=data['name'],
            building=data['building'],
            floor=data['floor'],
            altitude=data.get('altitude', 0),  # Sea level altitude
            floor_altitude=data['floor_altitude'],
            ceiling_height=data['ceiling_height'],
            gps_boundaries=data['gps_boundaries'],
            reference_pressure=data.get('reference_pressure'),
            center_latitude=data['center_latitude'],
            center_longitude=data['center_longitude'],
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
            'name', 'building', 'floor', 'altitude', 'floor_altitude',
            'ceiling_height', 'gps_boundaries', 'reference_pressure',
            'center_latitude', 'center_longitude', 'capacity', 'is_active'
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
        
        # Check if inside polygon
        is_inside = room.is_location_inside(data['latitude'], data['longitude'])
        
        # Calculate distance from center
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
        
        # Check altitude if provided
        altitude_valid = None
        if 'altitude' in data:
            altitude_valid = room.is_altitude_valid(data['altitude'])
        
        return success_response(
            data={
                'is_inside': is_inside,
                'distance_from_center': round(distance, 2),
                'altitude_valid': altitude_valid,
                'room': {
                    'name': room.name,
                    'floor': room.floor,
                    'floor_altitude': room.floor_altitude,
                    'ceiling_height': room.ceiling_height
                }
            }
        )
        
    except Exception as e:
        return error_response(f"Error checking location: {str(e)}", 500)

@rooms_bp.route('/record-path', methods=['POST'])
@jwt_required()
@admin_required
def record_room_path():
    """Record room boundaries by walking around it."""
    try:
        data = request.get_json()
        
        # Required: array of GPS points
        if 'path_points' not in data or not data['path_points']:
            return error_response("Path points required", 400)
        
        if 'room_name' not in data:
            return error_response("Room name required", 400)
        
        # Process path points to create polygon
        points = data['path_points']
        
        # Ensure at least 3 points
        if len(points) < 3:
            return error_response("At least 3 points required", 400)
        
        # Calculate center point
        lat_sum = sum(p['latitude'] for p in points)
        lng_sum = sum(p['longitude'] for p in points)
        center_lat = lat_sum / len(points)
        center_lng = lng_sum / len(points)
        
        # Create GPS boundaries
        gps_boundaries = [{'lat': p['latitude'], 'lng': p['longitude']} for p in points]
        
        # Get altitude data from first point
        first_point = points[0]
        
        # Create or update room
        room = Room.query.filter_by(name=data['room_name']).first()
        
        if room:
            # Update existing room
            room.gps_boundaries = gps_boundaries
            room.center_latitude = center_lat
            room.center_longitude = center_lng
            if 'altitude' in first_point:
                room.floor_altitude = first_point['altitude']
            if 'pressure' in first_point:
                room.reference_pressure = first_point['pressure']
        else:
            # Create new room
            room = Room(
                name=data['room_name'],
                building=data.get('building', 'Main'),
                floor=data.get('floor', 1),
                altitude=first_point.get('altitude', 0),
                floor_altitude=first_point.get('altitude', 0),
                ceiling_height=data.get('ceiling_height', 3.5),
                gps_boundaries=gps_boundaries,
                reference_pressure=first_point.get('pressure'),
                center_latitude=center_lat,
                center_longitude=center_lng,
                capacity=data.get('capacity', 30)
            )
            db.session.add(room)
        
        db.session.commit()
        
        return success_response(
            data={
                'room': room.to_dict(),
                'points_recorded': len(points),
                'area_center': {
                    'latitude': center_lat,
                    'longitude': center_lng
                }
            },
            message="Room boundaries recorded successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error recording room path: {str(e)}", 500)

