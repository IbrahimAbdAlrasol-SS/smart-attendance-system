"""Application entry point."""
import os
import click
from flask.cli import with_appcontext
from app import create_app, db
from dotenv import load_dotenv
load_dotenv()

import click
from flask.cli import with_appcontext
from app import create_app, db
"""Application entry point."""
import os


app = create_app(os.getenv('FLASK_ENV', 'development'))

@app.cli.command()
@with_appcontext
def create_db():
    """Create database tables."""
    db.create_all()
    click.echo('? Database tables created successfully!')

@app.cli.command()
@with_appcontext 
def drop_db():
    """Drop all database tables."""
    if click.confirm('Are you sure you want to drop all tables?'):
        db.drop_all()
        click.echo('??? Database tables dropped successfully!')

@app.cli.command()
@with_appcontext
def init_db():
    """Initialize database with sample data."""
    from app.models.user import User, UserRole, Section
    
    # Create admin user
    admin = User(
        email='admin@university.edu',
        name='System Administrator',
        role=UserRole.ADMIN
    )
    admin.set_password('admin123')
    admin.save()
    
    # Create teacher
    teacher = User(
        email='teacher@university.edu',
        name='Dr. Ahmed Hassan',
        role=UserRole.TEACHER,
        section=Section.A
    )
    teacher.set_password('teacher123')
    teacher.save()
    
    # Create student
    student = User(
        email='student@university.edu',
        name='ابراهيم',
        student_id='CS2021001',
        role=UserRole.STUDENT,
        section=Section.A
    )
    student.set_password('student123')
    student.save()
    
    click.echo(' Sample users created successfully!')
    click.echo(' Admin: admin@university.edu / admin123')
    click.echo('? Teacher: teacher@university.edu / teacher123')
    click.echo('? Student: student@university.edu / student123')

@app.cli.command()
@with_appcontext
def reset_db():
    """Reset database completely."""
    if click.confirm('Are you sure you want to reset the entire database?'):
        db.drop_all()
        db.create_all()
        click.echo(' Database reset complete!')

if __name__ == '__main__':
    # Development server
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(host=host, port=port, debug=debug)
