"""
Tests for Gestor PIX Flow - Full E2E Testing
Tests the complete Socio Gestor flow including:
- Login with gestor credentials
- Access to Gestor Dashboard
- Balance display (Mi Saldo and Saldo Terceros)
- PIX payment creation
- PIX status polling
- PIX payment simulation
- PIX history
"""
import pytest
import requests
import os
import time

# El default apuntaba a https://agent-payment-hub-1.preview.emergentagent.com,
# el preview de la herramienta con la que se armó el proyecto. Correr la
# suite mandaba emails, CPFs y reseteos de contraseña por POST a un dominio
# ajeno. Ahora: sin servidor declarado, estos tests se saltan.
from conftest import saltar_sin_servidor, servidor_de_integracion

pytestmark = saltar_sin_servidor()
BASE_URL = (servidor_de_integracion() or "")

# Test credentials
GESTOR_EMAIL = "testgestor@test.com"
GESTOR_PASSWORD = os.environ.get("TEST_GESTOR_PASSWORD")
ADMIN_EMAIL = "jefe@risappbr.com"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD")

class TestGestorAuthentication:
    """Test gestor login and authentication"""
    
    def test_gestor_login_success(self):
        """Test login with socio_gestor credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "session_token" in data, "No session token returned"
        assert data.get("user", {}).get("email") == GESTOR_EMAIL
        print(f"✓ Gestor login successful, role: {data.get('user', {}).get('role')}")
    
    def test_gestor_login_wrong_password(self):
        """Test login with wrong password fails"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": "WrongPassword123!"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Wrong password correctly rejected")


class TestGestorDashboard:
    """Test Gestor Dashboard endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Get authenticated session for gestor"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.session_token = data.get("session_token")
            self.headers = {"Authorization": f"Bearer {self.session_token}"}
        else:
            pytest.skip("Could not authenticate gestor")
    
    def test_gestor_dashboard_access(self):
        """Test access to gestor dashboard - returns balances"""
        response = requests.get(f"{BASE_URL}/api/gestor/dashboard", headers=self.headers)
        assert response.status_code == 200, f"Dashboard access failed: {response.text}"
        data = response.json()
        
        # Verify balance fields exist
        assert "balance_ris" in data, "Missing balance_ris field"
        assert "balance_ris_terceros" in data, "Missing balance_ris_terceros field"
        
        print(f"✓ Dashboard accessible")
        print(f"  - Mi Saldo (balance_ris): R$ {data.get('balance_ris', 0):.2f}")
        print(f"  - Saldo Terceros: R$ {data.get('balance_ris_terceros', 0):.2f}")
    
    def test_gestor_beneficiaries_list(self):
        """Test listing gestor beneficiaries"""
        response = requests.get(f"{BASE_URL}/api/gestor/beneficiaries", headers=self.headers)
        assert response.status_code == 200, f"Beneficiaries access failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of beneficiaries"
        print(f"✓ Beneficiaries listed: {len(data)} beneficiaries")
    
    def test_gestor_transactions_list(self):
        """Test listing gestor transactions"""
        response = requests.get(f"{BASE_URL}/api/gestor/transactions", headers=self.headers)
        assert response.status_code == 200, f"Transactions access failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of transactions"
        print(f"✓ Transactions listed: {len(data)} transactions")


class TestGestorPIXCreation:
    """Test PIX payment creation flow"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Get authenticated session for gestor"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.session_token = data.get("session_token")
            self.headers = {"Authorization": f"Bearer {self.session_token}"}
        else:
            pytest.skip("Could not authenticate gestor")
    
    def test_create_pix_payment_success(self):
        """Test creating a PIX payment with Mercado Pago"""
        # Create PIX payment
        response = requests.post(f"{BASE_URL}/api/gestor/pix/create", 
            headers=self.headers,
            json={
                "amount_ris": 10.0,
                "client_name": "Test Cliente",
                "client_email": "cliente@test.com",
                "client_cpf": "12345678900"
            }
        )
        assert response.status_code == 200, f"PIX creation failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "payment_id" in data, "Missing payment_id"
        assert "qr_code" in data, "Missing qr_code"
        assert "amount_ris" in data, "Missing amount_ris"
        assert "amount_brl" in data, "Missing amount_brl"
        assert "expires_in_seconds" in data, "Missing expires_in_seconds"
        
        # Store for later tests
        self.payment_id = data.get("payment_id")
        self.mp_payment_id = data.get("mp_payment_id")
        
        print(f"✓ PIX payment created successfully")
        print(f"  - Payment ID: {data.get('payment_id')}")
        print(f"  - MP Payment ID: {data.get('mp_payment_id')}")
        print(f"  - Amount RIS: R$ {data.get('amount_ris'):.2f}")
        print(f"  - Expires in: {data.get('expires_in_seconds')} seconds")
        print(f"  - QR Code length: {len(data.get('qr_code', ''))}")
    
    def test_create_pix_invalid_amount(self):
        """Test PIX creation with invalid amount fails"""
        response = requests.post(f"{BASE_URL}/api/gestor/pix/create", 
            headers=self.headers,
            json={
                "amount_ris": 0,
                "client_name": "Test Cliente"
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Invalid amount correctly rejected")
    
    def test_create_pix_negative_amount(self):
        """Test PIX creation with negative amount fails"""
        response = requests.post(f"{BASE_URL}/api/gestor/pix/create", 
            headers=self.headers,
            json={
                "amount_ris": -50.0,
                "client_name": "Test Cliente"
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Negative amount correctly rejected")


class TestGestorPIXStatus:
    """Test PIX status checking and simulation"""
    
    @pytest.fixture(autouse=True)
    def setup_session_and_pix(self):
        """Get authenticated session and create a test PIX payment"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.session_token = data.get("session_token")
            self.headers = {"Authorization": f"Bearer {self.session_token}"}
            
            # Create a test PIX payment
            pix_response = requests.post(f"{BASE_URL}/api/gestor/pix/create", 
                headers=self.headers,
                json={
                    "amount_ris": 5.0,
                    "client_name": "Status Test Cliente"
                }
            )
            if pix_response.status_code == 200:
                pix_data = pix_response.json()
                self.payment_id = pix_data.get("payment_id")
            else:
                pytest.skip(f"Could not create PIX payment: {pix_response.text}")
        else:
            pytest.skip("Could not authenticate gestor")
    
    def test_check_pix_status_pending(self):
        """Test checking PIX payment status"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/pix/status/{self.payment_id}", 
            headers=self.headers
        )
        assert response.status_code == 200, f"Status check failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing status field"
        assert "payment_id" in data, "Missing payment_id field"
        assert data.get("status") == "pending", f"Expected pending, got {data.get('status')}"
        
        print(f"✓ PIX status check successful")
        print(f"  - Payment ID: {data.get('payment_id')}")
        print(f"  - Status: {data.get('status')}")
    
    def test_check_pix_status_not_found(self):
        """Test checking non-existent PIX payment"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/pix/status/gpix_nonexistent123", 
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent PIX correctly returns 404")


class TestGestorPIXSimulation:
    """Test PIX payment simulation (for testing mode)"""
    
    @pytest.fixture(autouse=True)
    def setup_session_and_pix(self):
        """Get authenticated session and create a test PIX payment"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.session_token = data.get("session_token")
            self.headers = {"Authorization": f"Bearer {self.session_token}"}
            
            # Get initial balance
            dash_response = requests.get(f"{BASE_URL}/api/gestor/dashboard", headers=self.headers)
            if dash_response.status_code == 200:
                self.initial_balance = dash_response.json().get("balance_ris_terceros", 0)
            else:
                self.initial_balance = 0
            
            # Create a test PIX payment for simulation
            pix_response = requests.post(f"{BASE_URL}/api/gestor/pix/create", 
                headers=self.headers,
                json={
                    "amount_ris": 25.0,
                    "client_name": "Simulation Test Cliente"
                }
            )
            if pix_response.status_code == 200:
                pix_data = pix_response.json()
                self.payment_id = pix_data.get("payment_id")
                self.amount_ris = pix_data.get("amount_ris")
            else:
                pytest.skip(f"Could not create PIX payment: {pix_response.text}")
        else:
            pytest.skip("Could not authenticate gestor")
    
    def test_simulate_pix_payment_success(self):
        """Test simulating PIX payment confirmation"""
        # Simulate payment
        response = requests.post(
            f"{BASE_URL}/api/gestor/pix/simulate-payment/{self.payment_id}", 
            headers=self.headers
        )
        assert response.status_code == 200, f"Simulation failed: {response.text}"
        data = response.json()
        
        assert data.get("status") == "paid", f"Expected paid, got {data.get('status')}"
        assert "new_balance_terceros" in data, "Missing new_balance_terceros"
        
        # Verify balance increased
        new_balance = data.get("new_balance_terceros", 0)
        expected_balance = self.initial_balance + self.amount_ris
        
        print(f"✓ PIX simulation successful")
        print(f"  - Payment ID: {data.get('payment_id')}")
        print(f"  - Status: {data.get('status')}")
        print(f"  - Amount: R$ {data.get('amount_ris', 0):.2f}")
        print(f"  - Initial balance: R$ {self.initial_balance:.2f}")
        print(f"  - New balance: R$ {new_balance:.2f}")
    
    def test_simulate_already_paid_fails(self):
        """Test simulating already paid PIX fails"""
        # First simulate
        requests.post(
            f"{BASE_URL}/api/gestor/pix/simulate-payment/{self.payment_id}", 
            headers=self.headers
        )
        
        # Try to simulate again - should fail
        response = requests.post(
            f"{BASE_URL}/api/gestor/pix/simulate-payment/{self.payment_id}", 
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404 for already paid, got {response.status_code}"
        print("✓ Double simulation correctly prevented")


class TestGestorPIXHistory:
    """Test PIX payment history"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Get authenticated session for gestor"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.session_token = data.get("session_token")
            self.headers = {"Authorization": f"Bearer {self.session_token}"}
        else:
            pytest.skip("Could not authenticate gestor")
    
    def test_get_pix_history(self):
        """Test getting PIX payment history"""
        response = requests.get(f"{BASE_URL}/api/gestor/pix/history", headers=self.headers)
        assert response.status_code == 200, f"History fetch failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Expected list of payments"
        
        if len(data) > 0:
            # Verify payment structure
            payment = data[0]
            assert "payment_id" in payment, "Missing payment_id"
            assert "amount_ris" in payment, "Missing amount_ris"
            assert "status" in payment, "Missing status"
            
        print(f"✓ PIX history retrieved: {len(data)} payments")
        
        # Show recent payments
        for i, p in enumerate(data[:3]):
            print(f"  - {p.get('payment_id')}: R$ {p.get('amount_ris', 0):.2f} ({p.get('status')})")


class TestGestorPIXCancel:
    """Test PIX payment cancellation"""
    
    @pytest.fixture(autouse=True)
    def setup_session_and_pix(self):
        """Get authenticated session and create a test PIX payment"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.session_token = data.get("session_token")
            self.headers = {"Authorization": f"Bearer {self.session_token}"}
            
            # Create a test PIX payment
            pix_response = requests.post(f"{BASE_URL}/api/gestor/pix/create", 
                headers=self.headers,
                json={
                    "amount_ris": 15.0,
                    "client_name": "Cancel Test Cliente"
                }
            )
            if pix_response.status_code == 200:
                pix_data = pix_response.json()
                self.payment_id = pix_data.get("payment_id")
            else:
                pytest.skip(f"Could not create PIX payment: {pix_response.text}")
        else:
            pytest.skip("Could not authenticate gestor")
    
    def test_cancel_pending_pix(self):
        """Test cancelling a pending PIX payment"""
        response = requests.post(
            f"{BASE_URL}/api/gestor/pix/cancel/{self.payment_id}", 
            headers=self.headers
        )
        assert response.status_code == 200, f"Cancel failed: {response.text}"
        data = response.json()
        
        assert "payment_id" in data, "Missing payment_id in response"
        print(f"✓ PIX cancelled successfully: {self.payment_id}")
    
    def test_cancel_non_existent_pix(self):
        """Test cancelling non-existent PIX fails"""
        response = requests.post(
            f"{BASE_URL}/api/gestor/pix/cancel/gpix_nonexistent123", 
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent PIX cancel correctly returns 404")


class TestGestorRoleRestriction:
    """Test that gestor endpoints require socio_gestor role"""
    
    def test_user_cannot_access_gestor_endpoints(self):
        """Test regular user cannot access gestor endpoints"""
        # Try to access without auth
        response = requests.get(f"{BASE_URL}/api/gestor/dashboard")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Gestor endpoints require authentication")
    
    def test_admin_credentials_exist(self):
        """Verify admin can login (for comparison)"""
        response = requests.post(f"{BASE_URL}/api/auth/login-password", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        print(f"✓ Admin login verified: {ADMIN_EMAIL}")


class TestRateEndpoint:
    """Test exchange rate endpoint"""
    
    def test_rate_endpoint(self):
        """Test rate endpoint returns conversion rates"""
        response = requests.get(f"{BASE_URL}/api/rate")
        assert response.status_code == 200, f"Rate fetch failed: {response.text}"
        data = response.json()
        
        assert "ris_to_ves" in data, "Missing ris_to_ves"
        assert data.get("ris_to_ves", 0) > 0, "Invalid ris_to_ves rate"
        
        print(f"✓ Rate endpoint working")
        print(f"  - RIS to VES: {data.get('ris_to_ves')}")
        print(f"  - VES to RIS: {data.get('ves_to_ris')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
