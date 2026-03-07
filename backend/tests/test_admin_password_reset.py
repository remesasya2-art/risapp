"""
Test Admin Password Reset Flow
Testing features:
1. Admin can reset user password (admin_reset_user_password endpoint)
2. User receives temp password 
3. Login with temp password sets must_change_password flag
4. User can set new password via set_new_password endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pago-movil-app.preview.emergentagent.com/api')

# Test credentials
SUPER_ADMIN_EMAIL = "marshalljulio46@gmail.com"
SUPER_ADMIN_PASSWORD = "Admin2025!"
TEST_USER_EMAIL = "testuser123@test.com"
TEST_USER_ORIGINAL_PASSWORD = "TestPassword2025!"

class TestAdminPasswordResetFlow:
    """Tests for the complete admin password reset flow"""
    
    admin_token = None
    test_user_id = None
    temp_password = None
    user_token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as super admin and get test user ID"""
        # Login as admin
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        TestAdminPasswordResetFlow.admin_token = data["session_token"]
        
        # Verify admin role
        assert data["user"]["role"] == "super_admin", "User is not super_admin"
        
        # Get test user info
        headers = {"Authorization": f"Bearer {TestAdminPasswordResetFlow.admin_token}"}
        users_response = requests.get(f"{BASE_URL}/admin/users", headers=headers)
        assert users_response.status_code == 200, f"Failed to get users: {users_response.text}"
        
        users_data = users_response.json()
        for user in users_data.get("users", []):
            if user.get("email") == TEST_USER_EMAIL:
                TestAdminPasswordResetFlow.test_user_id = user.get("user_id")
                break
        
        if not TestAdminPasswordResetFlow.test_user_id:
            # Create test user if not exists
            register_response = requests.post(
                f"{BASE_URL}/auth/register",
                json={
                    "name": "Test User",
                    "email": TEST_USER_EMAIL,
                    "password": TEST_USER_ORIGINAL_PASSWORD,
                    "confirm_password": TEST_USER_ORIGINAL_PASSWORD
                }
            )
            # User might already exist, so just try to login
            login_test = requests.post(
                f"{BASE_URL}/auth/login-password",
                json={"email": TEST_USER_EMAIL, "password": TEST_USER_ORIGINAL_PASSWORD}
            )
            if login_test.status_code == 200:
                TestAdminPasswordResetFlow.test_user_id = login_test.json()["user"]["user_id"]
            else:
                pytest.skip("Test user could not be found or created")
        
        yield
    
    def test_01_admin_login_success(self):
        """Test: Super admin can login successfully"""
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_token" in data
        assert data["user"]["role"] == "super_admin"
        assert data["must_change_password"] == False
        print(f"✓ Admin logged in successfully, role: {data['user']['role']}")
    
    def test_02_admin_can_reset_user_password(self):
        """Test: Super admin can reset user password via /admin/reset-password"""
        headers = {"Authorization": f"Bearer {TestAdminPasswordResetFlow.admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/admin/reset-password",
            json={"user_id": TestAdminPasswordResetFlow.test_user_id},
            headers=headers
        )
        
        assert response.status_code == 200, f"Reset failed: {response.text}"
        data = response.json()
        
        # Verify response contains temp password
        assert "temp_password" in data, "Response missing temp_password"
        assert "message" in data, "Response missing message"
        assert len(data["temp_password"]) == 8, "Temp password should be 8 characters"
        
        TestAdminPasswordResetFlow.temp_password = data["temp_password"]
        print(f"✓ Password reset successful, temp password generated: {data['temp_password']}")
    
    def test_03_user_login_with_temp_password_returns_must_change_flag(self):
        """Test: User logging in with temp password gets must_change_password=True"""
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": TEST_USER_EMAIL, "password": TestAdminPasswordResetFlow.temp_password}
        )
        
        assert response.status_code == 200, f"Login with temp password failed: {response.text}"
        data = response.json()
        
        # Verify must_change_password flag is True
        assert data.get("must_change_password") == True, "must_change_password should be True"
        assert "session_token" in data, "Response missing session_token"
        
        TestAdminPasswordResetFlow.user_token = data["session_token"]
        print(f"✓ User logged in with temp password, must_change_password={data['must_change_password']}")
    
    def test_04_user_can_set_new_password(self):
        """Test: User can set new password via /auth/set-new-password"""
        headers = {"Authorization": f"Bearer {TestAdminPasswordResetFlow.user_token}"}
        new_password = "NewTest2025!#"
        
        response = requests.post(
            f"{BASE_URL}/auth/set-new-password",
            json={
                "new_password": new_password,
                "confirm_password": new_password
            },
            headers=headers
        )
        
        assert response.status_code == 200, f"Set new password failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"✓ User set new password successfully: {data['message']}")
    
    def test_05_user_login_with_new_password_no_must_change_flag(self):
        """Test: User can login with new password and must_change_password is False"""
        new_password = "NewTest2025!#"
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": TEST_USER_EMAIL, "password": new_password}
        )
        
        assert response.status_code == 200, f"Login with new password failed: {response.text}"
        data = response.json()
        
        # Verify must_change_password is now False
        assert data.get("must_change_password") == False, "must_change_password should be False after change"
        print(f"✓ User logged in with new password, must_change_password={data['must_change_password']}")
    
    def test_06_set_new_password_fails_when_not_required(self):
        """Test: set-new-password fails if user doesn't need to change password"""
        # Login again to get fresh token
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": TEST_USER_EMAIL, "password": "NewTest2025!#"}
        )
        assert response.status_code == 200
        token = response.json()["session_token"]
        
        # Try to set new password when not required
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            f"{BASE_URL}/auth/set-new-password",
            json={
                "new_password": "AnotherPass2025!",
                "confirm_password": "AnotherPass2025!"
            },
            headers=headers
        )
        
        assert response.status_code == 400, "Should fail when password change not required"
        print(f"✓ Set new password correctly rejected when not required")
    
    def test_07_admin_cannot_reset_admin_password(self):
        """Test: Admin cannot reset password of another admin"""
        headers = {"Authorization": f"Bearer {TestAdminPasswordResetFlow.admin_token}"}
        
        # Get admin user ID
        users_response = requests.get(f"{BASE_URL}/admin/users", headers=headers)
        admin_user_id = None
        for user in users_response.json().get("users", []):
            if user.get("role") in ["admin", "super_admin"] and user.get("email") != SUPER_ADMIN_EMAIL:
                admin_user_id = user.get("user_id")
                break
        
        if not admin_user_id:
            # Try with own ID
            admin_user_id = "user_0f38b78bce8e"  # Known super_admin ID
        
        response = requests.post(
            f"{BASE_URL}/admin/reset-password",
            json={"user_id": admin_user_id},
            headers=headers
        )
        
        # Should fail with 400
        assert response.status_code == 400, f"Should not be able to reset admin password: {response.text}"
        print(f"✓ Correctly prevented admin password reset")


class TestLoginFlow:
    """Basic login flow tests"""
    
    def test_login_with_valid_credentials(self):
        """Test: Login with valid email and password"""
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "session_token" in data
        assert "user" in data
        assert "must_change_password" in data
        assert data["user"]["email"] == SUPER_ADMIN_EMAIL
        print(f"✓ Login successful with valid credentials")
    
    def test_login_with_invalid_password(self):
        """Test: Login fails with wrong password"""
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": "WrongPassword123!"}
        )
        assert response.status_code == 401
        print(f"✓ Login correctly rejected invalid password")
    
    def test_login_with_nonexistent_email(self):
        """Test: Login fails with non-existent email"""
        response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": "nonexistent@test.com", "password": "Password123!"}
        )
        assert response.status_code == 401
        print(f"✓ Login correctly rejected non-existent email")


class TestAuthMeEndpoint:
    """Test /auth/me endpoint"""
    
    def test_auth_me_returns_user_data(self):
        """Test: /auth/me returns user data with must_change_password"""
        # Login first
        login_response = requests.post(
            f"{BASE_URL}/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        token = login_response.json()["session_token"]
        
        # Call /auth/me
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify key fields exist
        assert "user_id" in data
        assert "email" in data
        assert "role" in data
        assert "password_set" in data
        print(f"✓ /auth/me returns user data correctly")
    
    def test_auth_me_unauthorized_without_token(self):
        """Test: /auth/me fails without token"""
        response = requests.get(f"{BASE_URL}/auth/me")
        assert response.status_code == 401
        print(f"✓ /auth/me correctly requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
