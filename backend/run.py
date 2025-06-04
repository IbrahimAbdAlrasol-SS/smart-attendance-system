# File: backend/run.py
"""Application entry point."""
import os
import click
from flask.cli import with_appcontext
from app import create_app, db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create Flask app
app = create_app(os.getenv('FLASK_ENV', 'development'))

@app.cli.command()
@with_appcontext
def create_db():
    """Create database tables."""
    db.create_all()
    click.echo('✅ Database tables created successfully!')

@app.cli.command()
@with_appcontext 
def drop_db():
    """Drop all database tables."""
    if click.confirm('Are you sure you want to drop all tables?'):
        db.drop_all()
        click.echo('❌ Database tables dropped successfully!')

@app.cli.command()
@with_appcontext
def init_db():
    """Initialize database with sample data."""
    from app.models.user import User, UserRole, Section
    
    # Create super admin
    super_admin = User.query.filter_by(email='super@admin.com').first()
    if not super_admin:
        super_admin = User(
            email='super@admin.com',
            name='Super Admin',
            role=UserRole.SUPER_ADMIN
        )
        super_admin.set_password('super123456')
        db.session.add(super_admin)
    
    # Create admin
    admin = User.query.filter_by(email='admin@university.edu').first()
    if not admin:
        admin = User(
            email='admin@university.edu',
            name='System Administrator',
            role=UserRole.ADMIN
        )
        admin.set_password('admin123456')
        db.session.add(admin)
    
    # Create teachers
    teachers = [
        ('د. أحمد حسن', 'ahmed.hassan@university.edu', 'teacher123'),
        ('د. فاطمة علي', 'fatima.ali@university.edu', 'teacher123'),
        ('د. محمد إبراهيم', 'mohammed.ibrahim@university.edu', 'teacher123')
    ]
    
    for name, email, password in teachers:
        teacher = User.query.filter_by(email=email).first()
        if not teacher:
            teacher = User(
                email=email,
                name=name,
                role=UserRole.TEACHER
            )
            teacher.set_password(password)
            db.session.add(teacher)
    
    db.session.commit()
    
    click.echo('✅ Sample users created successfully!')
    click.echo('👤 Super Admin: super@admin.com / super123456')
    click.echo('👤 Admin: admin@university.edu / admin123456')
    click.echo('👨‍🏫 Teachers: ahmed.hassan@university.edu / teacher123')

@app.cli.command()
@with_appcontext
def seed_all():
    """Seed database with complete test data."""
    from app.services.seed_service import SeedService
    
    try:
        SeedService.seed_all()
        click.echo('✅ Database seeded successfully with test data!')
    except Exception as e:
        click.echo(f'❌ Error seeding database: {str(e)}')

@app.cli.command()
@with_appcontext
def reset_db():
    """Reset database completely."""
    if click.confirm('This will delete all data and recreate tables. Continue?'):
        db.drop_all()
        db.create_all()
        click.echo('✅ Database reset complete!')
        
        if click.confirm('Initialize with sample data?'):
            init_db()

if __name__ == '__main__':
    # Development server
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(host=host, port=port, debug=debug)
