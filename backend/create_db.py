from app import create_app, db
from app.models.user import User, UserRole, Section

app = create_app('development')
with app.app_context():
    print('🔄 Creating SQLite database...')
    db.create_all()
    print('✅ Database tables created!')
    
    print('👤 Creating users...')
    admin = User(email='admin@university.edu', name='مدير النظام', role=UserRole.ADMIN)
    admin.set_password('admin123')
    admin.save()
    
    teacher = User(email='teacher@university.edu', name='د. أحمد حسن', role=UserRole.TEACHER, section=Section.A)
    teacher.set_password('teacher123')
    teacher.save()
    
    student = User(email='student@university.edu', name='محمد علي أحمد', student_id='CS2021001', role=UserRole.STUDENT, section=Section.A)
    student.set_password('student123')
    student.save()
    
    print('🎯 Sample users created successfully!')
    print('👤 Admin: admin@university.edu / admin123')
    print('👨‍🏫 Teacher: teacher@university.edu / teacher123')
    print('👨‍🎓 Student: student@university.edu / student123')