# backend/update_database.py
"""Script to update database with new fields."""
from app import create_app, db
from sqlalchemy import text

app = create_app('development')

with app.app_context():
    print("🔄 Updating database schema...")
    
    try:
        # Add location fields to lectures table
        with db.engine.connect() as conn:
            # Check if columns exist before adding
            result = conn.execute(text("PRAGMA table_info(lectures)"))
            columns = [row[1] for row in result]
            
            if 'latitude' not in columns:
                conn.execute(text("ALTER TABLE lectures ADD COLUMN latitude REAL DEFAULT 33.3152"))
                print("✅ Added latitude to lectures")
            
            if 'longitude' not in columns:
                conn.execute(text("ALTER TABLE lectures ADD COLUMN longitude REAL DEFAULT 44.3661"))
                print("✅ Added longitude to lectures")
            
            # Update attendance_records table
            result = conn.execute(text("PRAGMA table_info(attendance_records)"))
            columns = [row[1] for row in result]
            
            if 'verification_method' not in columns:
                conn.execute(text("ALTER TABLE attendance_records ADD COLUMN verification_method VARCHAR(20) DEFAULT 'qr'"))
                print("✅ Added verification_method to attendance_records")
            
            if 'notes' not in columns:
                conn.execute(text("ALTER TABLE attendance_records ADD COLUMN notes TEXT"))
                print("✅ Added notes to attendance_records")
            
            if 'latitude' not in columns:
                conn.execute(text("ALTER TABLE attendance_records ADD COLUMN latitude REAL"))
                print("✅ Added latitude to attendance_records")
            
            if 'longitude' not in columns:
                conn.execute(text("ALTER TABLE attendance_records ADD COLUMN longitude REAL"))
                print("✅ Added longitude to attendance_records")
            
            if 'approved_by' not in columns:
                conn.execute(text("ALTER TABLE attendance_records ADD COLUMN approved_by INTEGER"))
                print("✅ Added approved_by to attendance_records")
            
            if 'approved_at' not in columns:
                conn.execute(text("ALTER TABLE attendance_records ADD COLUMN approved_at DATETIME"))
                print("✅ Added approved_at to attendance_records")
            
            conn.commit()
        
        print("✅ Database schema updated successfully!")
        
    except Exception as e:
        print(f"❌ Error updating database: {str(e)}")
        print("💡 Try deleting the database file and recreating it:")