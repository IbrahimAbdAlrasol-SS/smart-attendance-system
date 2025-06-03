# إنشاء اختبار Authentication

"""Test authentication endpoints."""
import json
import pytest
from app import create_app, db
from app.models.user import User, UserRole

@pytest.fixture
def app():
    """Create test app."""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

@pytest.fixture
def sample_user(app):
    """Create sample user for testing."""
    with app.app_context():
        user = User(
            email='test@example.com',
            name='Test User',
            role=UserRole.STUDENT
        )
        user.set_password('password123')
        user.save()
        return user

def test_health_check(client):
    """Test auth health endpoint."""
    response = client.get('/api/auth/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == 'Auth service is running'

def test_register_success(client):
    """Test successful user registration."""
    response = client.post('/api/auth/register', 
        json={
            'email': 'newuser@example.com',
            'password': 'password123',
            'name': 'New User'
        })
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['error'] == False
    assert 'data' in data
    assert data['data']['email'] == 'newuser@example.com'

def test_register_validation(client):
    """Test registration validation."""
    # Missing fields
    response = client.post('/api/auth/register', json={})
    assert response.status_code == 400
    
    # Invalid email
    response = client.post('/api/auth/register', 
        json={
            'email': 'invalid-email',
            'password': 'password123',
            'name': 'Test User'
        })
    assert response.status_code == 400

def test_login_success(client, sample_user):
    """Test successful login."""
    response = client.post('/api/auth/login',
        json={
            'email': 'test@example.com',
            'password': 'password123'
        })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['error'] == False
    assert 'access_token' in data['data']
    assert 'user' in data['data']

def test_login_invalid_credentials(client, sample_user):
    """Test login with invalid credentials."""
    response = client.post('/api/auth/login',
        json={
            'email': 'test@example.com',
            'password': 'wrongpassword'
        })
    
    assert response.status_code == 401

def test_get_current_user(client, sample_user):
    """Test get current user profile."""
    # First login to get token
    login_response = client.post('/api/auth/login',
        json={
            'email': 'test@example.com',
            'password': 'password123'
        })
    
    token = json.loads(login_response.data)['data']['access_token']
    
    # Test profile endpoint
    response = client.get('/api/auth/me',
        headers={'Authorization': f'Bearer {token}'})
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['error'] == False
    assert data['data']['email'] == 'test@example.com'
