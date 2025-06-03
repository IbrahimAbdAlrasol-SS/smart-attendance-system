from app import create_app, db
from app.models.user import User, UserRole

app = create_app("development")
with app.app_context():
    print("🔄 Testing basic setup...")
    
    # إنشاء الجداول
    db.create_all()
    print("✅ Database created!")
    
    # إنشاء مستخدم واحد فقط
    user = User(
        email="test@test.com",
        name="Test User",
        role=UserRole.STUDENT
    )
    user.set_password("123456")
    user.save()
    
    print("✅ User created!")
    print("📊 Database working!")