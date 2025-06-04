# File: backend/app/services/seed_service.py
"""Database seeding service for test data."""
from app import db
from app.models.user import User, UserRole
from app.models.student import Student, StudyType, Section
from app.models.room import Room
from app.models.schedule import Schedule, WeekDay
from datetime import datetime, time
import random

class SeedService:
    """Service to seed database with test data."""
    
    @staticmethod
    def seed_all():
        """Seed all test data."""
        SeedService.seed_rooms()
        SeedService.seed_teachers()
        SeedService.seed_students()
        SeedService.seed_schedules()
    
    @staticmethod
    def seed_rooms():
        """Seed test rooms with 3D data."""
        buildings = ['المبنى الرئيسي', 'مبنى الحاسبات', 'مبنى الهندسة']
        
        for building_idx, building in enumerate(buildings):
            for floor in range(1, 4):  # 3 floors each
                for room_num in range(1, 4):  # 3 rooms per floor
                    room_name = f"{chr(65 + building_idx)}{floor}0{room_num}"
                    
                    # Create polygon boundaries (rectangular room)
                    base_lat = 33.3152 + (building_idx * 0.001)
                    base_lng = 44.3661 + (room_num * 0.001)
                    
                    boundaries = [
                        {"lat": base_lat, "lng": base_lng},
                        {"lat": base_lat + 0.0001, "lng": base_lng},
                        {"lat": base_lat + 0.0001, "lng": base_lng + 0.0001},
                        {"lat": base_lat, "lng": base_lng + 0.0001}
                    ]
                    
                    room = Room(
                        name=room_name,
                        building=building,
                        floor=floor,
                        altitude=280 + (floor * 3.5),  # Baghdad altitude + floor height
                        floor_altitude=(floor - 1) * 3.5,  # Height from ground
                        ceiling_height=3.5,
                        center_latitude=base_lat + 0.00005,
                        center_longitude=base_lng + 0.00005,
                        capacity=30 + (room_num * 5),
                        gps_boundaries=boundaries,
                        reference_pressure=1013.25 - (floor * 0.12)  # Pressure decreases with altitude
                    )
                    db.session.add(room)
        
        db.session.commit()
        print(f"✅ Created {Room.query.count()} rooms")
    
    @staticmethod
    def seed_teachers():
        """Seed test teachers."""
        teachers_data = [
            ('د. أحمد حسن', 'ahmed.hassan', 'teacher123'),
            ('د. فاطمة علي', 'fatima.ali', 'teacher123'),
            ('د. محمد إبراهيم', 'mohammed.ibrahim', 'teacher123'),
            ('د. زينب خالد', 'zainab.khalid', 'teacher123'),
            ('د. عمر سالم', 'omar.salem', 'teacher123')
        ]
        
        for name, username, password in teachers_data:
            teacher = User(
                email=f"{username}@university.edu",
                name=name,
                role=UserRole.TEACHER
            )
            teacher.set_password(password)
            db.session.add(teacher)
        
        db.session.commit()
        print(f"✅ Created {len(teachers_data)} teachers")
    
    @staticmethod  
    def seed_students():
        """Seed test students in bulk."""
        from app.services.student_service import StudentService
        
        sections = ['A', 'B', 'C']
        study_types = ['morning', 'evening']
        
        # Arabic names for realistic data
        first_names = ['أحمد', 'محمد', 'علي', 'عمر', 'حسين', 'فاطمة', 'زينب', 'مريم', 'نور', 'سارة']
        middle_names = ['عبد الله', 'حسن', 'علي', 'محمد', 'إبراهيم', 'خالد', 'سالم', 'جمال', 'كريم']
        last_names = ['الحسني', 'العراقي', 'البغدادي', 'الكربلائي', 'النجفي', 'البصري', 'الموصلي']
        
        students_created = []
        
        for section in sections:
            for study_year in range(1, 5):  # 4 years
                for i in range(10):  # 10 students per section per year
                    full_name = f"{random.choice(first_names)} {random.choice(middle_names)} {random.choice(last_names)}"
                    
                    result, error = StudentService.create_student(
                        full_name=full_name,
                        section=section,
                        study_year=study_year,
                        study_type=random.choice(study_types),
                        department='CS',
                        is_repeater=random.random() < 0.1,  # 10% repeaters
                        failed_subjects=['Math101', 'CS201'] if random.random() < 0.05 else []
                    )
                    
                    if result:
                        students_created.append(result['credentials'])
        
        print(f"✅ Created {len(students_created)} students")
        
        # Save credentials to file for testing
        with open('test_students_credentials.txt', 'w', encoding='utf-8') as f:
            f.write("=== Test Student Credentials ===\n\n")
            for cred in students_created[:10]:  # First 10 only
                f.write(f"University ID: {cred['university_id']}\n")
                f.write(f"Secret Code: {cred['secret_code']}\n")
                f.write(f"Email: {cred['email']}\n")
                f.write("-" * 30 + "\n")
    
    @staticmethod
    def seed_schedules():
        """Seed test schedules."""
        subjects = [
            ('البرمجة المتقدمة', 'CS301'),
            ('قواعد البيانات', 'CS302'),
            ('الذكاء الاصطناعي', 'CS401'),
            ('شبكات الحاسوب', 'CS303'),
            ('هندسة البرمجيات', 'CS402')
        ]
        
        teachers = User.query.filter_by(role=UserRole.TEACHER).all()
        rooms = Room.query.filter_by(is_active=True).all()
        
        for section in [Section.A, Section.B, Section.C]:
            for study_year in range(1, 5):
                for day_idx, day in enumerate([WeekDay.SUNDAY, WeekDay.MONDAY, WeekDay.TUESDAY]):
                    start_hour = 8
                    
                    for subject_idx in range(2):  # 2 subjects per day
                        if subject_idx + (study_year - 1) * 2 < len(subjects):
                            subject_name, subject_code = subjects[subject_idx + (study_year - 1) * 2]
                            
                            schedule = Schedule(
                                subject_name=subject_name,
                                subject_code=subject_code,
                                teacher_id=random.choice(teachers).id,
                                room_id=random.choice(rooms).id,
                                section=section,
                                study_year=study_year,
                                study_type=StudyType.MORNING,
                                day_of_week=day,
                                start_time=time(start_hour + subject_idx * 2, 0),
                                end_time=time(start_hour + subject_idx * 2 + 1, 30),
                                semester=1,
                                academic_year="2024-2025"
                            )
                            db.session.add(schedule)
        
        db.session.commit()
        print(f"✅ Created {Schedule.query.count()} schedules")