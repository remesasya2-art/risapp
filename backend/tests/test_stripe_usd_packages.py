"""
Test Suite for Stripe USD Recharge Packages
Tests the USD→RIS rate functionality and Stripe package endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://agent-payment-hub-1.preview.emergentagent.com/api').rstrip('/')

# Test credentials
ADMIN_EMAIL = "marshalljulio46@gmail.com"
ADMIN_PASSWORD = "Admin2025!"


class TestRateEndpoint:
    """Tests for GET /api/rate endpoint - USD rates"""
    
    def test_rate_returns_usd_to_ris(self):
        """Verify /api/rate returns usd_to_ris field"""
        response = requests.get(f"{BASE_URL}/rate")
        assert response.status_code == 200
        
        data = response.json()
        assert "usd_to_ris" in data, "usd_to_ris field missing from rate response"
        assert isinstance(data["usd_to_ris"], (int, float))
        assert data["usd_to_ris"] > 0
        print(f"✓ usd_to_ris = {data['usd_to_ris']}")
    
    def test_rate_returns_ris_to_usd(self):
        """Verify /api/rate returns ris_to_usd field"""
        response = requests.get(f"{BASE_URL}/rate")
        assert response.status_code == 200
        
        data = response.json()
        assert "ris_to_usd" in data, "ris_to_usd field missing from rate response"
        assert isinstance(data["ris_to_usd"], (int, float))
        assert data["ris_to_usd"] > 0
        print(f"✓ ris_to_usd = {data['ris_to_usd']}")
    
    def test_rate_returns_ves_rates(self):
        """Verify /api/rate still returns VES rates"""
        response = requests.get(f"{BASE_URL}/rate")
        assert response.status_code == 200
        
        data = response.json()
        assert "ris_to_ves" in data, "ris_to_ves field missing"
        assert "ves_to_ris" in data, "ves_to_ris field missing"
        print(f"✓ ris_to_ves = {data['ris_to_ves']}, ves_to_ris = {data['ves_to_ris']}")
    
    def test_rate_usd_ris_inverse_relationship(self):
        """Verify usd_to_ris and ris_to_usd are inverses"""
        response = requests.get(f"{BASE_URL}/rate")
        assert response.status_code == 200
        
        data = response.json()
        usd_to_ris = data["usd_to_ris"]
        ris_to_usd = data["ris_to_usd"]
        
        # Check inverse relationship (with tolerance for floating point)
        expected_inverse = 1 / usd_to_ris
        assert abs(ris_to_usd - expected_inverse) < 0.001, f"ris_to_usd ({ris_to_usd}) should be inverse of usd_to_ris ({usd_to_ris})"
        print(f"✓ Inverse relationship verified: 1/{usd_to_ris} ≈ {ris_to_usd}")


class TestStripePackagesEndpoint:
    """Tests for GET /api/payments/stripe/packages endpoint"""
    
    def test_packages_endpoint_returns_200(self):
        """Verify packages endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/payments/stripe/packages")
        assert response.status_code == 200
        print("✓ Packages endpoint accessible")
    
    def test_packages_returns_usd_currency(self):
        """Verify packages are in USD currency"""
        response = requests.get(f"{BASE_URL}/payments/stripe/packages")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("currency") == "USD", f"Expected currency USD, got {data.get('currency')}"
        print("✓ Currency is USD")
    
    def test_packages_returns_current_rate(self):
        """Verify packages include current exchange rate"""
        response = requests.get(f"{BASE_URL}/payments/stripe/packages")
        assert response.status_code == 200
        
        data = response.json()
        assert "current_rate" in data, "current_rate missing from response"
        assert data["current_rate"] > 0
        print(f"✓ Current rate = {data['current_rate']}")
    
    def test_packages_has_four_options(self):
        """Verify there are 4 USD packages ($10, $25, $50, $100)"""
        response = requests.get(f"{BASE_URL}/payments/stripe/packages")
        assert response.status_code == 200
        
        data = response.json()
        packages = data.get("packages", [])
        assert len(packages) == 4, f"Expected 4 packages, got {len(packages)}"
        
        amounts = [pkg["amount_usd"] for pkg in packages]
        assert 10 in amounts, "$10 package missing"
        assert 25 in amounts, "$25 package missing"
        assert 50 in amounts, "$50 package missing"
        assert 100 in amounts, "$100 package missing"
        print(f"✓ All 4 packages present: ${amounts}")
    
    def test_packages_have_correct_bonuses(self):
        """Verify bonus percentages: $10=0%, $25=5%, $50=10%, $100=15%"""
        response = requests.get(f"{BASE_URL}/payments/stripe/packages")
        assert response.status_code == 200
        
        data = response.json()
        packages = {pkg["amount_usd"]: pkg for pkg in data.get("packages", [])}
        
        assert packages[10]["bonus_percent"] == 0, "$10 should have 0% bonus"
        assert packages[25]["bonus_percent"] == 5, "$25 should have 5% bonus"
        assert packages[50]["bonus_percent"] == 10, "$50 should have 10% bonus"
        assert packages[100]["bonus_percent"] == 15, "$100 should have 15% bonus"
        print("✓ Bonus percentages correct: 0%, 5%, 10%, 15%")
    
    def test_packages_ris_calculation_correct(self):
        """Verify RIS calculation: amount_usd * usd_to_ris * (1 + bonus/100)"""
        response = requests.get(f"{BASE_URL}/payments/stripe/packages")
        assert response.status_code == 200
        
        data = response.json()
        rate = data["current_rate"]
        
        for pkg in data.get("packages", []):
            expected_base = pkg["amount_usd"] * rate
            expected_bonus = expected_base * (pkg["bonus_percent"] / 100)
            expected_total = expected_base + expected_bonus
            
            # Allow small floating point tolerance
            assert abs(pkg["base_ris"] - expected_base) < 0.01, f"base_ris mismatch for ${pkg['amount_usd']}"
            assert abs(pkg["bonus_ris"] - expected_bonus) < 0.01, f"bonus_ris mismatch for ${pkg['amount_usd']}"
            assert abs(pkg["total_ris"] - expected_total) < 0.01, f"total_ris mismatch for ${pkg['amount_usd']}"
            
            print(f"✓ ${pkg['amount_usd']}: {pkg['base_ris']} + {pkg['bonus_ris']} = {pkg['total_ris']} RIS")
    
    def test_packages_include_exchange_rate(self):
        """Verify each package includes the exchange rate used"""
        response = requests.get(f"{BASE_URL}/payments/stripe/packages")
        assert response.status_code == 200
        
        data = response.json()
        current_rate = data["current_rate"]
        
        for pkg in data.get("packages", []):
            assert "exchange_rate" in pkg, f"exchange_rate missing from package {pkg['id']}"
            assert pkg["exchange_rate"] == current_rate, f"Package rate mismatch"
        
        print("✓ All packages include exchange_rate")


class TestAdminRateUpdate:
    """Tests for POST /api/admin/settings/rate endpoint"""
    
    @pytest.fixture
    def admin_session(self):
        """Get admin session token"""
        response = requests.post(f"{BASE_URL}/auth/login-password", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("session_token")
    
    def test_admin_can_update_usd_to_ris(self, admin_session):
        """Verify admin can update usd_to_ris rate"""
        # Get current rate
        rate_response = requests.get(f"{BASE_URL}/rate")
        original_rate = rate_response.json().get("usd_to_ris", 5.5)
        
        # Update to new rate
        new_rate = 6.0
        response = requests.post(
            f"{BASE_URL}/admin/settings/rate",
            headers={"Authorization": f"Bearer {admin_session}"},
            json={"ris_to_ves": 92.0, "usd_to_ris": new_rate}
        )
        assert response.status_code == 200
        assert response.json().get("usd_to_ris") == new_rate
        print(f"✓ Rate updated to {new_rate}")
        
        # Verify rate was persisted
        verify_response = requests.get(f"{BASE_URL}/rate")
        assert verify_response.json().get("usd_to_ris") == new_rate
        print("✓ Rate persisted in database")
        
        # Restore original rate
        requests.post(
            f"{BASE_URL}/admin/settings/rate",
            headers={"Authorization": f"Bearer {admin_session}"},
            json={"ris_to_ves": 92.0, "usd_to_ris": original_rate}
        )
        print(f"✓ Rate restored to {original_rate}")
    
    def test_rate_update_affects_packages(self, admin_session):
        """Verify updating rate changes package RIS calculations"""
        # Get original packages
        original_packages = requests.get(f"{BASE_URL}/payments/stripe/packages").json()
        original_rate = original_packages["current_rate"]
        
        # Update rate
        new_rate = 7.0
        requests.post(
            f"{BASE_URL}/admin/settings/rate",
            headers={"Authorization": f"Bearer {admin_session}"},
            json={"ris_to_ves": 92.0, "usd_to_ris": new_rate}
        )
        
        # Get updated packages
        updated_packages = requests.get(f"{BASE_URL}/payments/stripe/packages").json()
        
        assert updated_packages["current_rate"] == new_rate
        
        # Verify $10 package calculation changed
        pkg_10_original = next(p for p in original_packages["packages"] if p["amount_usd"] == 10)
        pkg_10_updated = next(p for p in updated_packages["packages"] if p["amount_usd"] == 10)
        
        assert pkg_10_updated["base_ris"] == 10 * new_rate
        assert pkg_10_updated["base_ris"] != pkg_10_original["base_ris"]
        print(f"✓ $10 package: {pkg_10_original['base_ris']} RIS → {pkg_10_updated['base_ris']} RIS")
        
        # Restore original rate
        requests.post(
            f"{BASE_URL}/admin/settings/rate",
            headers={"Authorization": f"Bearer {admin_session}"},
            json={"ris_to_ves": 92.0, "usd_to_ris": original_rate}
        )
        print(f"✓ Rate restored to {original_rate}")
    
    def test_unauthenticated_cannot_update_rate(self):
        """Verify unauthenticated users cannot update rate"""
        response = requests.post(
            f"{BASE_URL}/admin/settings/rate",
            json={"ris_to_ves": 92.0, "usd_to_ris": 10.0}
        )
        assert response.status_code == 401
        print("✓ Unauthenticated request rejected")


class TestStripeCheckoutEndpoint:
    """Tests for POST /api/payments/stripe/checkout endpoint"""
    
    @pytest.fixture
    def user_session(self):
        """Get a user session token"""
        # Try to login as admin (who is also a user)
        response = requests.post(f"{BASE_URL}/auth/login-password", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("User login failed")
        return response.json().get("session_token")
    
    def test_checkout_requires_auth(self):
        """Verify checkout requires authentication"""
        response = requests.post(
            f"{BASE_URL}/payments/stripe/checkout",
            json={"package_id": "usd_10", "origin_url": "https://example.com"}
        )
        assert response.status_code == 401
        print("✓ Checkout requires authentication")
    
    def test_checkout_invalid_package(self, user_session):
        """Verify checkout rejects invalid package ID"""
        response = requests.post(
            f"{BASE_URL}/payments/stripe/checkout",
            headers={"Authorization": f"Bearer {user_session}"},
            json={"package_id": "invalid_package", "origin_url": "https://example.com"}
        )
        assert response.status_code == 400
        print("✓ Invalid package rejected")
    
    def test_checkout_creates_session(self, user_session):
        """Verify checkout creates Stripe session with valid package"""
        response = requests.post(
            f"{BASE_URL}/payments/stripe/checkout",
            headers={"Authorization": f"Bearer {user_session}"},
            json={"package_id": "usd_10", "origin_url": "https://example.com", "for_terceros": False}
        )
        
        # Should return 200 with checkout URL (or 503 if Stripe not configured)
        if response.status_code == 503:
            pytest.skip("Stripe not configured")
        
        assert response.status_code == 200
        data = response.json()
        assert "checkout_url" in data
        assert "session_id" in data
        assert data["checkout_url"].startswith("https://checkout.stripe.com")
        print(f"✓ Checkout session created: {data['session_id'][:20]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
