
import requests
import json

BASE_URL = "http://127.0.0.1:5000/api/auth"

def test_auth():
    print("🧪 Testing Authentication System...")
    
    # 1. Test Health Check
    print("1️⃣ Testing Health Check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print()
    
    # 2. Test Registration
    print("2️⃣ Testing Registration...")
    register_data = {
        "email": "testuser@example.com",
        "password": "123456",
        "name": "Test User"
    }
    response = requests.post(f"{BASE_URL}/register", json=register_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print()
    
    # 3. Test Login
    print("3️⃣ Testing Login...")
    login_data = {
        "email": "testuser@example.com",
        "password": "123456"
    }
    response = requests.post(f"{BASE_URL}/login", json=login_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        token = response.json()["data"]["access_token"]
        
        # 4. Test Profile
        print("4️⃣ Testing User Profile...")
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/me", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_auth()
