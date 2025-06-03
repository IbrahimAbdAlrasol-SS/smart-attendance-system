import os
import sys

# إجبار استخدام SQLite
os.environ['DATABASE_URL'] = 'sqlite:///smart_attendance_dev.db'
os.environ['FLASK_ENV'] = 'development'

# تحديث مسار Python
sys.path.insert(0, '.')

from app import create_app, db
from app.models.user import User, UserRole, Section

print('🔄 Creating SQLite database...')
app = create_app('development')

with app.app_context():
    print('📊 App config:', app.config.get('SQLALCHEMY_DATABASE_URI'))
    
    # إنشاء الجداول
    db.create_all()
    print('✅ Database tables created!')
    
    # إنشاء المستخدمين
    print('👤 Creating users...')
    
    # مدير النظام
    admin = User(
        email='admin@university.edu', 
        name='مدير النظام', 
        role=UserRole.ADMIN
    )
    admin.set_password('admin123')
    admin.save()
    
    # أستاذ
    teacher = User(
        email='teacher@university.edu', 
        name='د. أحمد حسن', 
        role=UserRole.TEACHER, 
        section=Section.A
    )
    teacher.set_password('teacher123')
    teacher.save()
    
    # طالب
    student = User(
        email='student@university.edu', 
        name='محمد علي أحمد', 
        student_id='CS2021001', 
        role=UserRole.STUDENT, 
        section=Section.A
    )
    student.set_password('student123')
    student.save()
    
    print('🎯 Sample users created successfully!')
    print('👤 Admin: admin@university.edu / admin123')
    print('👨‍🏫 Teacher: teacher@university.edu / teacher123')
    print('👨‍🎓 Student: student@university.edu / student123')
    
    print('📁 Database file: smart_attendance_dev.db')