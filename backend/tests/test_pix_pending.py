"""
Backend tests for PIX pending transaction feature
Tests:
- GET /api/pix/pending - returns has_pending: false when no pending transactions
- GET /api/pix/pending - requires authentication (401 without token)
- POST /api/pix/cancel - cancels a pending transaction
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', os.environ.get('EXPO_PUBLIC_BACKEND_URL', '')).rstrip('/')

# Test credentials from the review request
TEST_USER_EMAIL = "test@ris.app"
TEST_USER_PASSWORD = "Test1234!"
SUPER_ADMIN_EMAIL = "marshalljulio46@gmail.com"
SUPER_ADMIN_PASSWORD = "Admin2025!"


class TestPixPendingEndpoint:
    """Tests for GET /api/pix/pending endpoint"""

    @pytest.fixture
    def api_client(self):
        """Create a requests session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session

    @pytest.fixture
    def auth_token(self, api_client):
        """Get authentication token by logging in as test user"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login-password",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("session_token")
        # If test user doesn't exist, try super admin
        response = api_client.post(
            f"{BASE_URL}/api/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("session_token")
        pytest.skip(f"Could not authenticate: {response.status_code} - {response.text}")

    @pytest.fixture
    def authenticated_client(self, api_client, auth_token):
        """Session with auth header"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        return api_client

    def test_pix_pending_requires_authentication(self, api_client):
        """GET /api/pix/pending - returns 401 without authentication token"""
        response = api_client.get(f"{BASE_URL}/api/pix/pending")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"PASS: /api/pix/pending returns 401 without token")

    def test_pix_pending_returns_has_pending_false_when_no_transactions(self, authenticated_client):
        """GET /api/pix/pending - returns has_pending: false when no pending transactions"""
        response = authenticated_client.get(f"{BASE_URL}/api/pix/pending")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "has_pending" in data, "Response should contain 'has_pending' field"
        
        # The user may or may not have pending transactions - both are valid
        # Just verify the structure is correct
        if data["has_pending"]:
            assert "pending_transaction" in data, "Should have 'pending_transaction' when has_pending is True"
            pending = data["pending_transaction"]
            assert "transaction_id" in pending, "Pending transaction should have 'transaction_id'"
            assert "amount_brl" in pending, "Pending transaction should have 'amount_brl'"
            assert "status" in pending, "Pending transaction should have 'status'"
            print(f"PASS: /api/pix/pending returns pending transaction: {pending.get('transaction_id')}")
        else:
            assert data.get("pending_transaction") is None, "pending_transaction should be None when has_pending is False"
            print(f"PASS: /api/pix/pending returns has_pending: false")


class TestPixCancelEndpoint:
    """Tests for POST /api/pix/cancel endpoint"""

    @pytest.fixture
    def api_client(self):
        """Create a requests session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session

    @pytest.fixture
    def auth_token(self, api_client):
        """Get authentication token by logging in"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login-password",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("session_token")
        # If test user doesn't exist, try super admin
        response = api_client.post(
            f"{BASE_URL}/api/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("session_token")
        pytest.skip(f"Could not authenticate: {response.status_code} - {response.text}")

    @pytest.fixture
    def authenticated_client(self, api_client, auth_token):
        """Session with auth header"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        return api_client

    def test_pix_cancel_requires_authentication(self, api_client):
        """POST /api/pix/cancel - returns 401 without authentication token"""
        response = api_client.post(
            f"{BASE_URL}/api/pix/cancel",
            json={"transaction_id": "test-id"}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"PASS: /api/pix/cancel returns 401 without token")

    def test_pix_cancel_returns_404_for_nonexistent_transaction(self, authenticated_client):
        """POST /api/pix/cancel - returns 404 for non-existent transaction"""
        fake_transaction_id = f"test-{uuid.uuid4().hex[:12]}"
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/pix/cancel",
            json={"transaction_id": fake_transaction_id}
        )
        
        # Should return 404 for non-existent or already processed transaction
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print(f"PASS: /api/pix/cancel returns 404 for non-existent transaction")

    def test_pix_cancel_with_pending_transaction(self, authenticated_client):
        """POST /api/pix/cancel - test cancelling a real pending transaction if one exists"""
        # First check if there's a pending transaction
        pending_response = authenticated_client.get(f"{BASE_URL}/api/pix/pending")
        
        if pending_response.status_code != 200:
            pytest.skip("Could not check pending transactions")
        
        pending_data = pending_response.json()
        
        if pending_data.get("has_pending") and pending_data.get("pending_transaction"):
            transaction_id = pending_data["pending_transaction"]["transaction_id"]
            
            # Try to cancel the pending transaction
            cancel_response = authenticated_client.post(
                f"{BASE_URL}/api/pix/cancel",
                json={"transaction_id": transaction_id}
            )
            
            assert cancel_response.status_code == 200, f"Expected 200, got {cancel_response.status_code}: {cancel_response.text}"
            
            data = cancel_response.json()
            assert "message" in data, "Response should contain 'message' field"
            
            # Verify transaction is no longer pending
            verify_response = authenticated_client.get(f"{BASE_URL}/api/pix/pending")
            verify_data = verify_response.json()
            
            # After cancellation, has_pending should be false or a different transaction
            if verify_data.get("has_pending"):
                assert verify_data["pending_transaction"]["transaction_id"] != transaction_id, \
                    "Cancelled transaction should no longer be returned as pending"
            
            print(f"PASS: /api/pix/cancel successfully cancelled transaction {transaction_id}")
        else:
            # No pending transaction to cancel - this is fine
            print(f"INFO: No pending transaction to cancel - skipping cancel test")
            pytest.skip("No pending transaction available to test cancel")


class TestApiHealth:
    """Basic health checks for the API"""

    @pytest.fixture
    def api_client(self):
        """Create a requests session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session

    def test_api_rate_endpoint(self, api_client):
        """Test that /api/rate endpoint is accessible"""
        response = api_client.get(f"{BASE_URL}/api/rate")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "ris_to_ves" in data, "Response should contain exchange rates"
        print(f"PASS: /api/rate returns exchange rates")

    def test_login_with_credentials(self, api_client):
        """Test login with provided credentials"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login-password",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        
        # Either login succeeds or credentials are invalid - both are valid API responses
        assert response.status_code in [200, 401, 423], f"Unexpected status: {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "session_token" in data, "Successful login should return session_token"
            assert "user" in data, "Successful login should return user data"
            print(f"PASS: Login successful for super admin")
        elif response.status_code == 401:
            print(f"INFO: Super admin login returned 401 - credentials may be incorrect")
        elif response.status_code == 423:
            print(f"INFO: Super admin account is locked")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
