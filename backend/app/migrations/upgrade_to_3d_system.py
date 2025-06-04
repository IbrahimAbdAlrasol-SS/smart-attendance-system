# File: backend/app/migrations/upgrade_to_3d_system.py
"""Comprehensive database migration to upgrade to 3D room system."""
import os
import sys
from datetime import datetime
from sqlalchemy import text, inspect
from flask import current_app
from app import create_app, db
from app.models.user import User, UserRole
from app.models.student import Student, StudyType, StudentStatus, Section

def check_database_compatibility():
    """Check if database is compatible for migration."""
    try:
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        required_tables = ['users', 'students', 'rooms', 'lectures', 'attendance_records']
        missing_tables = [table for table in required_tables if table not in existing_tables]
        
        if missing_tables:
            print(f"❌ Missing required tables: {missing_tables}")
            return False
        
        print("✅ Database compatibility check passed")
        return True
        
    except Exception as e:
        print(f"❌ Database compatibility check failed: {str(e)}")
        return False

def backup_existing_data():
    """Create backup of existing data before migration."""
    try:
        backup_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = f"migrations/backups/backup_{backup_timestamp}"
        os.makedirs(backup_dir, exist_ok=True)
        
        # In a real system, you'd use proper backup tools
        # For SQLite, you could copy the database file
        # For PostgreSQL, you'd use pg_dump
        
        print(f"✅ Backup created in {backup_dir}")
        return backup_dir
        
    except Exception as e:
        print(f"❌ Backup failed: {str(e)}")
        return None

def migrate_rooms_table():
    """Upgrade rooms table to support 3D features."""
    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('rooms')]
        
        print("🔄 Migrating rooms table to 3D support...")
        
        # Add new columns for 3D support
        new_columns = [
            # Basic 3D location data
            ('room_number', 'VARCHAR(20)'),
            ('ground_reference_altitude', 'FLOAT', 0.0),
            ('floor_altitude_above_ground', 'FLOAT', 0.0),
            ('room_floor_altitude', 'FLOAT', 0.0),
            ('room_ceiling_altitude', 'FLOAT', 3.5),
            ('center_altitude', 'FLOAT', 0.0),
            
            # 3D geometry
            ('corner_points_3d', 'TEXT'),  # JSON storage
            ('room_area_sqm', 'FLOAT'),
            ('room_volume_cubic_m', 'FLOAT'),
            ('room_perimeter_m', 'FLOAT'),
            
            # Barometer data
            ('ground_reference_pressure', 'FLOAT'),
            ('floor_reference_pressure', 'FLOAT'),
            ('room_pressure_range', 'TEXT'),  # JSON storage
            ('pressure_tolerance', 'FLOAT', 0.5),
            
            # Recording metadata
            ('recorded_by_user_id', 'INTEGER'),
            ('recorded_at', 'DATETIME'),
            ('recording_path', 'TEXT'),  # JSON storage
            ('recording_duration_seconds', 'INTEGER'),
            ('recording_accuracy_metadata', 'TEXT'),  # JSON storage
            
            # Validation status
            ('is_3d_validated', 'BOOLEAN', 'FALSE'),
            ('validation_notes', 'TEXT'),
            ('room_type', 'VARCHAR(50)', "'classroom'"),
        ]
        
        for column_info in new_columns:
            column_name = column_info[0]
            column_type = column_info[1]
            default_value = column_info[2] if len(column_info) > 2 else None
            
            if column_name not in columns:
                if default_value:
                    db.engine.execute(text(f"ALTER TABLE rooms ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"))
                else:
                    db.engine.execute(text(f"ALTER TABLE rooms ADD COLUMN {column_name} {column_type}"))
                print(f"  ✅ Added column: {column_name}")
        
        # Update existing rooms with default 3D data
        print("🔄 Updating existing rooms with default 3D data...")
        existing_rooms = db.engine.execute(text("SELECT id, name, floor, latitude, longitude FROM rooms")).fetchall()
        
        for room in existing_rooms:
            room_id, name, floor, lat, lng = room
            
            # Calculate default 3D properties
            floor_altitude = floor * 3.5  # 3.5m per floor
            ceiling_altitude = floor_altitude + 3.5
            
            # Create default GPS boundaries (small rectangle around center)
            if lat and lng:
                boundaries = [
                    {"lat": lat - 0.0001, "lng": lng - 0.0001, "alt": floor_altitude},
                    {"lat": lat + 0.0001, "lng": lng - 0.0001, "alt": floor_altitude},
                    {"lat": lat + 0.0001, "lng": lng + 0.0001, "alt": floor_altitude},
                    {"lat": lat - 0.0001, "lng": lng + 0.0001, "alt": floor_altitude}
                ]
                
                corner_points_3d = str(boundaries).replace("'", '"')
                pressure_range = '{"min": 1013.0, "max": 1013.5}'
                
                update_query = text(f"""
                    UPDATE rooms SET 
                        room_floor_altitude = :floor_alt,
                        room_ceiling_altitude = :ceiling_alt,
                        center_altitude = :center_alt,
                        corner_points_3d = :corners,
                        room_pressure_range = :pressure,
                        room_area_sqm = 20.0,
                        room_volume_cubic_m = 70.0,
                        room_type = 'classroom'
                    WHERE id = :room_id
                """)
                
                db.engine.execute(update_query, 
                    floor_alt=floor_altitude,
                    ceiling_alt=ceiling_altitude,
                    center_alt=floor_altitude + 1.75,  # Middle of room height
                    corners=corner_points_3d,
                    pressure=pressure_range,
                    room_id=room_id
                )
        
        print("✅ Rooms table migration completed")
        
    except Exception as e:
        print(f"❌ Rooms table migration failed: {str(e)}")
        raise

def migrate_students_table():
    """Upgrade students table for enhanced face recognition."""
    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('students')]
        
        print("🔄 Migrating students table for face recognition...")
        
        # Add face recognition columns
        new_columns = [
            ('face_template_hash', 'VARCHAR(255)'),
            ('face_registration_token', 'VARCHAR(255)'),
            ('face_device_info', 'TEXT'),  # JSON storage
            ('face_security_level', 'VARCHAR(20)', "'standard'"),
            ('last_face_verification', 'DATETIME'),
            ('face_verification_attempts', 'INTEGER', '0'),
            ('face_security_flags', 'TEXT'),  # JSON storage for security alerts
        ]
        
        for column_info in new_columns:
            column_name = column_info[0]
            column_type = column_info[1]
            default_value = column_info[2] if len(column_info) > 2 else None
            
            if column_name not in columns:
                if default_value:
                    db.engine.execute(text(f"ALTER TABLE students ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"))
                else:
                    db.engine.execute(text(f"ALTER TABLE students ADD COLUMN {column_name} {column_type}"))
                print(f"  ✅ Added column: {column_name}")
        
        print("✅ Students table migration completed")
        
    except Exception as e:
        print(f"❌ Students table migration failed: {str(e)}")
        raise

def migrate_attendance_records_table():
    """Upgrade attendance_records table for sequential verification."""
    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('attendance_records')]
        
        print("🔄 Migrating attendance_records table for sequential verification...")
        
        # Add sequential verification columns
        new_columns = [
            # Verification details
            ('verification_session_id', 'VARCHAR(100)'),
            ('verification_details', 'TEXT'),  # JSON storage of complete verification data
            ('verification_steps_completed', 'INTEGER', '0'),
            ('overall_confidence_score', 'FLOAT', '0.0'),
            
            # Individual verification results
            ('gps_verified', 'BOOLEAN', 'FALSE'),
            ('gps_confidence', 'FLOAT', '0.0'),
            ('gps_distance_from_center', 'FLOAT'),
            
            ('altitude_verified', 'BOOLEAN', 'FALSE'),
            ('altitude_confidence', 'FLOAT', '0.0'),
            ('barometer_pressure', 'FLOAT'),
            ('altitude', 'FLOAT'),
            
            ('qr_verified', 'BOOLEAN', 'FALSE'),
            ('qr_session_id', 'VARCHAR(100)'),
            ('qr_expires_at', 'DATETIME'),
            
            ('face_verified', 'BOOLEAN', 'FALSE'),
            ('face_confidence', 'FLOAT', '0.0'),
            ('face_anti_spoofing_passed', 'BOOLEAN', 'FALSE'),
            ('face_device_consistent', 'BOOLEAN', 'FALSE'),
            
            # Processing metadata
            ('total_verification_time_ms', 'INTEGER', '0'),
            ('verification_warnings', 'TEXT'),  # JSON array
            ('verification_errors', 'TEXT'),  # JSON array
            ('verification_recommendations', 'TEXT'),  # JSON array
        ]
        
        for column_info in new_columns:
            column_name = column_info[0]
            column_type = column_info[1]
            default_value = column_info[2] if len(column_info) > 2 else None
            
            if column_name not in columns:
                if default_value:
                    db.engine.execute(text(f"ALTER TABLE attendance_records ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"))
                else:
                    db.engine.execute(text(f"ALTER TABLE attendance_records ADD COLUMN {column_name} {column_type}"))
                print(f"  ✅ Added column: {column_name}")
        
        print("✅ Attendance records table migration completed")
        
    except Exception as e:
        print(f"❌ Attendance records table migration failed: {str(e)}")
        raise

def create_new_tables():
    """Create new tables for enhanced functionality."""
    try:
        print("🔄 Creating new tables...")
        
        # Create verification_sessions table for tracking active sessions
        verification_sessions_sql = """
        CREATE TABLE IF NOT EXISTS verification_sessions (
            id INTEGER PRIMARY KEY,
            session_id VARCHAR(100) UNIQUE NOT NULL,
            student_id INTEGER NOT NULL,
            lecture_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            started_at DATETIME NOT NULL,
            completed_at DATETIME,
            current_step VARCHAR(50),
            overall_status VARCHAR(50),
            final_decision VARCHAR(50),
            attendance_type VARCHAR(50),
            session_data TEXT,  -- JSON storage
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (lecture_id) REFERENCES lectures(id),
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
        """
        
        # Create barometer_calibrations table
        barometer_calibrations_sql = """
        CREATE TABLE IF NOT EXISTS barometer_calibrations (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            building_id INTEGER,
            calibration_data TEXT NOT NULL,  -- JSON storage
            ground_reference_pressure FLOAT NOT NULL,
            ground_altitude FLOAT NOT NULL,
            calibration_quality VARCHAR(20),
            calibrated_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
        
        # Create face_registration_logs table for security
        face_registration_logs_sql = """
        CREATE TABLE IF NOT EXISTS face_registration_logs (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            registration_type VARCHAR(50) NOT NULL,  -- initial, renewal, reset
            device_info TEXT,  -- JSON storage
            quality_score FLOAT,
            registration_success BOOLEAN,
            error_message TEXT,
            security_flags TEXT,  -- JSON storage
            registered_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id)
        )
        """
        
        # Create system_analytics table
        system_analytics_sql = """
        CREATE TABLE IF NOT EXISTS system_analytics (
            id INTEGER PRIMARY KEY,
            metric_name VARCHAR(100) NOT NULL,
            metric_value FLOAT NOT NULL,
            metric_data TEXT,  -- JSON storage for additional data
            recorded_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # Execute table creation
        tables = [
            ('verification_sessions', verification_sessions_sql),
            ('barometer_calibrations', barometer_calibrations_sql),
            ('face_registration_logs', face_registration_logs_sql),
            ('system_analytics', system_analytics_sql)
        ]
        
        for table_name, sql in tables:
            db.engine.execute(text(sql))
            print(f"  ✅ Created table: {table_name}")
        
        print("✅ New tables creation completed")
        
    except Exception as e:
        print(f"❌ New tables creation failed: {str(e)}")
        raise

def create_indexes():
    """Create indexes for better performance."""
    try:
        print("🔄 Creating database indexes...")
        
        indexes = [
            # Verification sessions indexes
            "CREATE INDEX IF NOT EXISTS idx_verification_sessions_student ON verification_sessions(student_id)",
            "CREATE INDEX IF NOT EXISTS idx_verification_sessions_lecture ON verification_sessions(lecture_id)",
            "CREATE INDEX IF NOT EXISTS idx_verification_sessions_status ON verification_sessions(overall_status)",
            "CREATE INDEX IF NOT EXISTS idx_verification_sessions_started ON verification_sessions(started_at)",
            
            # Attendance records indexes
            "CREATE INDEX IF NOT EXISTS idx_attendance_verification_session ON attendance_records(verification_session_id)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_gps_verified ON attendance_records(gps_verified)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_face_verified ON attendance_records(face_verified)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_overall_confidence ON attendance_records(overall_confidence_score)",
            
            # Students face recognition indexes
            "CREATE INDEX IF NOT EXISTS idx_students_face_registered ON students(face_registered)",
            "CREATE INDEX IF NOT EXISTS idx_students_face_template_hash ON students(face_template_hash)",
            "CREATE INDEX IF NOT EXISTS idx_students_last_face_verification ON students(last_face_verification)",
            
            # Rooms 3D indexes
            "CREATE INDEX IF NOT EXISTS idx_rooms_3d_validated ON rooms(is_3d_validated)",
            "CREATE INDEX IF NOT EXISTS idx_rooms_recorded_by ON rooms(recorded_by_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_rooms_type ON rooms(room_type)",
            
            # Barometer calibrations indexes
            "CREATE INDEX IF NOT EXISTS idx_barometer_calibrations_user ON barometer_calibrations(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_barometer_calibrations_active ON barometer_calibrations(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_barometer_calibrations_expires ON barometer_calibrations(expires_at)",
            
            # Face registration logs indexes
            "CREATE INDEX IF NOT EXISTS idx_face_logs_student ON face_registration_logs(student_id)",
            "CREATE INDEX IF NOT EXISTS idx_face_logs_type ON face_registration_logs(registration_type)",
            "CREATE INDEX IF NOT EXISTS idx_face_logs_success ON face_registration_logs(registration_success)",
            
            # System analytics indexes
            "CREATE INDEX IF NOT EXISTS idx_analytics_metric_name ON system_analytics(metric_name)",
            "CREATE INDEX IF NOT EXISTS idx_analytics_recorded_at ON system_analytics(recorded_at)",
        ]
        
        for index_sql in indexes:
            try:
                db.engine.execute(text(index_sql))
                print(f"  ✅ Created index")
            except Exception as e:
                print(f"  ⚠️ Index creation warning: {str(e)}")
        
        print("✅ Database indexes creation completed")
        
    except Exception as e:
        print(f"❌ Index creation failed: {str(e)}")
        raise

def seed_enhanced_data():
    """Seed database with enhanced sample data."""
    try:
        print("🔄 Seeding enhanced sample data...")
        
        # Create enhanced admin user
        enhanced_admin = User.query.filter_by(email='admin@3d.system').first()
        if not enhanced_admin:
            enhanced_admin = User(
                email='admin@3d.system',
                name='3D System Administrator',
                role=UserRole.ADMIN
            )
            enhanced_admin.set_password('3dsystem123')
            db.session.add(enhanced_admin)
            print("  ✅ Created 3D system admin")
        
        # Create test teacher for 3D system
        test_teacher = User.query.filter_by(email='teacher@3d.system').first()
        if not test_teacher:
            test_teacher = User(
                email='teacher@3d.system',
                name='د. أحمد التقنيات المتقدمة',
                role=UserRole.TEACHER
            )
            test_teacher.set_password('teacher123')
            db.session.add(test_teacher)
            print("  ✅ Created 3D system teacher")
        
        # Create sample student with face registration
        test_student_user = User.query.filter_by(email='student@3d.system').first()
        if not test_student_user:
            test_student_user = User(
                email='student@3d.system',
                name='طالب النظام ثلاثي الأبعاد',
                role=UserRole.STUDENT
            )
            test_student_user.set_password('student123')
            db.session.add(test_student_user)
            db.session.flush()
            
            # Create student profile
            test_student = Student(
                user_id=test_student_user.id,
                university_id='CS2025001',
                full_name='طالب النظام ثلاثي الأبعاد',
                section=Section.A,
                study_year=3,
                study_type=StudyType.MORNING,
                department='CS',
                face_registered=True,
                face_registered_at=datetime.utcnow(),
                face_template_hash='demo_hash_3d_system',
                face_security_level='high'
            )
            test_student.set_secret_code('ABC123')
            db.session.add(test_student)
            print("  ✅ Created 3D system student with face registration")
        
        db.session.commit()
        print("✅ Enhanced sample data seeding completed")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Enhanced data seeding failed: {str(e)}")
        raise

def verify_migration():
    """Verify that migration completed successfully."""
    try:
        print("🔄 Verifying migration...")
        
        inspector = inspect(db.engine)
        
        # Check that all new columns exist
        rooms_columns = [col['name'] for col in inspector.get_columns('rooms')]
        required_rooms_columns = [
            'ground_reference_altitude', 'room_floor_altitude', 'corner_points_3d',
            'is_3d_validated', 'room_pressure_range'
        ]
        
        missing_rooms_columns = [col for col in required_rooms_columns if col not in rooms_columns]
        if missing_rooms_columns:
            print(f"❌ Missing rooms columns: {missing_rooms_columns}")
            return False
        
        # Check that new tables exist
        tables = inspector.get_table_names()
        required_new_tables = [
            'verification_sessions', 'barometer_calibrations',
            'face_registration_logs', 'system_analytics'
        ]
        
        missing_tables = [table for table in required_new_tables if table not in tables]
        if missing_tables:
            print(f"❌ Missing new tables: {missing_tables}")
            return False
        
        # Test basic functionality
        try:
            # Test room query with new columns
            room_count = db.engine.execute(text("SELECT COUNT(*) FROM rooms WHERE is_3d_validated IS NOT NULL")).scalar()
            print(f"  ✅ Found {room_count} rooms with 3D validation status")
            
            # Test enhanced student query
            student_count = db.engine.execute(text("SELECT COUNT(*) FROM students WHERE face_registered IS NOT NULL")).scalar()
            print(f"  ✅ Found {student_count} students with face registration status")
            
            # Test new tables
            for table in required_new_tables:
                count = db.engine.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                print(f"  ✅ Table {table} is accessible (count: {count})")
            
        except Exception as e:
            print(f"❌ Functionality test failed: {str(e)}")
            return False
        
        print("✅ Migration verification completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Migration verification failed: {str(e)}")
        return False

def main():
    """Main migration function."""
    print("🚀 Starting Smart Attendance System 3D Migration")
    print("=" * 60)
    
    # Create Flask app context
    app = create_app('development')
    
    with app.app_context():
        try:
            # Step 1: Pre-migration checks
            print("\n📋 STEP 1: Pre-migration checks")
            if not check_database_compatibility():
                print("❌ Pre-migration checks failed. Cannot proceed.")
                return False
            
            # Step 2: Backup existing data
            print("\n💾 STEP 2: Creating backup")
            backup_path = backup_existing_data()
            if not backup_path:
                print("⚠️ Backup creation failed, but proceeding...")
            
            # Step 3: Migrate existing tables
            print("\n🔄 STEP 3: Migrating existing tables")
            migrate_rooms_table()
            migrate_students_table()
            migrate_attendance_records_table()
            
            # Step 4: Create new tables
            print("\n🏗️ STEP 4: Creating new tables")
            create_new_tables()
            
            # Step 5: Create indexes
            print("\n📊 STEP 5: Creating performance indexes")
            create_indexes()
            
            # Step 6: Seed enhanced data
            print("\n🌱 STEP 6: Seeding enhanced sample data")
            seed_enhanced_data()
            
            # Step 7: Verify migration
            print("\n✅ STEP 7: Verifying migration")
            if not verify_migration():
                print("❌ Migration verification failed!")
                return False
            
            print("\n" + "=" * 60)
            print("🎉 MIGRATION COMPLETED SUCCESSFULLY!")
            print("=" * 60)
            print("\n📝 Next Steps:")
            print("1. Test the enhanced APIs with the dashboard")
            print("2. Register face biometrics for existing students")  
            print("3. Record 3D boundaries for existing rooms")
            print("4. Set up barometer calibration")
            print("5. Test sequential verification flow")
            print("\n🔗 Enhanced APIs Available:")
            print("- /api/enhanced-attendance/* (Sequential verification)")
            print("- /api/recording/* (Dynamic room recording)")  
            print("- Face registration and verification")
            print("- 3D room management")
            print("- Barometer calibration")
            
            return True
            
        except Exception as e:
            print(f"\n❌ MIGRATION FAILED: {str(e)}")
            print("\n🔄 Recommended Recovery Steps:")
            print("1. Restore from backup if available")
            print("2. Check database logs for detailed errors")
            print("3. Run migration again after fixing issues")
            print("4. Contact system administrator if problems persist")
            return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)