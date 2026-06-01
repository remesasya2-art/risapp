"""
Password Recovery API Tests
Tests for the 3-step password recovery flow and support contact form
"""
import pytest
import requests
import os
import random
import string

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://agent-payment-hub-1.preview.emergentagent.com').rstrip('/')

# Test user credentials (must exist in database)
TEST_USER = {
    "email": "testrecovery@ris.app",
    "full_name": "Usuario Prueba Recovery",
    "phone_number": "+5511999999999",
    "cpf": "12345678901",
    "document_number": "V12345678"
}


class TestVerifyIdentityEndpoint:
    """Tests for POST /api/recovery/verify-identity - Step 1"""
    
    def test_verify_identity_success(self):
        """Test successful identity verification with correct data"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": TEST_USER["email"],
            "full_name": TEST_USER["full_name"],
            "phone_number": TEST_USER["phone_number"],
            "cpf": TEST_USER["cpf"],
            "document_number": TEST_USER["document_number"]
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["success"] == True
        assert "email_masked" in data
        assert "message" in data
        # Verify email is masked correctly
        assert "***" in data["email_masked"]
    
    def test_verify_identity_wrong_email(self):
        """Test identity verification with non-existent email"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": "nonexistent@test.com",
            "full_name": TEST_USER["full_name"],
            "phone_number": TEST_USER["phone_number"],
            "cpf": TEST_USER["cpf"],
            "document_number": TEST_USER["document_number"]
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "correo" in data["detail"].lower() or "cuenta" in data["detail"].lower()
    
    def test_verify_identity_wrong_name(self):
        """Test identity verification with wrong name"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": TEST_USER["email"],
            "full_name": "Wrong Name",
            "phone_number": TEST_USER["phone_number"],
            "cpf": TEST_USER["cpf"],
            "document_number": TEST_USER["document_number"]
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "nombre" in data["detail"].lower()
    
    def test_verify_identity_wrong_cpf(self):
        """Test identity verification with wrong CPF"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": TEST_USER["email"],
            "full_name": TEST_USER["full_name"],
            "phone_number": TEST_USER["phone_number"],
            "cpf": "99999999999",
            "document_number": TEST_USER["document_number"]
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "cpf" in data["detail"].lower()
    
    def test_verify_identity_wrong_document(self):
        """Test identity verification with wrong document number"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": TEST_USER["email"],
            "full_name": TEST_USER["full_name"],
            "phone_number": TEST_USER["phone_number"],
            "cpf": TEST_USER["cpf"],
            "document_number": "WRONG123"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "documento" in data["detail"].lower()
    
    def test_verify_identity_missing_fields(self):
        """Test identity verification with missing required fields"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": TEST_USER["email"]
        })
        
        assert response.status_code == 422  # Validation error


class TestVerifyCodeEndpoint:
    """Tests for POST /api/recovery/verify-code - Step 2"""
    
    def test_verify_code_no_pending_request(self):
        """Test code verification without pending recovery request"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-code", json={
            "email": "random@test.com",
            "code": "123456"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "pendiente" in data["detail"].lower() or "solicitud" in data["detail"].lower()
    
    def test_verify_code_wrong_code(self):
        """Test code verification with wrong code (after identity verification)"""
        # First, verify identity to create a recovery request
        requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": TEST_USER["email"],
            "full_name": TEST_USER["full_name"],
            "phone_number": TEST_USER["phone_number"],
            "cpf": TEST_USER["cpf"],
            "document_number": TEST_USER["document_number"]
        })
        
        # Try with wrong code
        response = requests.post(f"{BASE_URL}/api/recovery/verify-code", json={
            "email": TEST_USER["email"],
            "code": "000000"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "incorrecto" in data["detail"].lower() or "intento" in data["detail"].lower()
    
    def test_verify_code_missing_fields(self):
        """Test code verification with missing fields"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-code", json={
            "email": TEST_USER["email"]
        })
        
        assert response.status_code == 422


class TestResetPasswordEndpoint:
    """Tests for POST /api/recovery/reset-password - Step 3"""
    
    def test_reset_password_invalid_token(self):
        """Test password reset with invalid token"""
        response = requests.post(f"{BASE_URL}/api/recovery/reset-password", json={
            "email": TEST_USER["email"],
            "recovery_token": "invalid_token_12345",
            "new_password": "NewPass123!"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "token" in data["detail"].lower() or "inválido" in data["detail"].lower()
    
    def test_reset_password_weak_password_no_uppercase(self):
        """Test password reset with password missing uppercase"""
        response = requests.post(f"{BASE_URL}/api/recovery/reset-password", json={
            "email": TEST_USER["email"],
            "recovery_token": "some_token",
            "new_password": "newpass123"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "mayúscula" in data["detail"].lower()
    
    def test_reset_password_weak_password_no_lowercase(self):
        """Test password reset with password missing lowercase"""
        response = requests.post(f"{BASE_URL}/api/recovery/reset-password", json={
            "email": TEST_USER["email"],
            "recovery_token": "some_token",
            "new_password": "NEWPASS123"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "minúscula" in data["detail"].lower()
    
    def test_reset_password_weak_password_no_number(self):
        """Test password reset with password missing number"""
        response = requests.post(f"{BASE_URL}/api/recovery/reset-password", json={
            "email": TEST_USER["email"],
            "recovery_token": "some_token",
            "new_password": "NewPassWord"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "número" in data["detail"].lower()
    
    def test_reset_password_weak_password_too_short(self):
        """Test password reset with password too short"""
        response = requests.post(f"{BASE_URL}/api/recovery/reset-password", json={
            "email": TEST_USER["email"],
            "recovery_token": "some_token",
            "new_password": "Pass1"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "8" in data["detail"] or "caracteres" in data["detail"].lower()
    
    def test_reset_password_missing_fields(self):
        """Test password reset with missing fields"""
        response = requests.post(f"{BASE_URL}/api/recovery/reset-password", json={
            "email": TEST_USER["email"]
        })
        
        assert response.status_code == 422


class TestSupportContactEndpoint:
    """Tests for POST /api/recovery/support-contact"""
    
    def test_support_contact_success(self):
        """Test successful support contact submission"""
        response = requests.post(f"{BASE_URL}/api/recovery/support-contact", json={
            "email": "test@example.com",
            "subject": "Problema con recuperación",
            "phone_number": "+5511999999999",
            "message": "Necesito ayuda para recuperar mi cuenta. No recuerdo mis datos."
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["success"] == True
        assert "ticket_id" in data
        assert data["ticket_id"].startswith("sup_")
    
    def test_support_contact_message_too_long(self):
        """Test support contact with message exceeding 200 characters"""
        long_message = "A" * 201
        response = requests.post(f"{BASE_URL}/api/recovery/support-contact", json={
            "email": "test@example.com",
            "subject": "Test",
            "phone_number": "+5511999999999",
            "message": long_message
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "200" in data["detail"]
    
    def test_support_contact_message_too_short(self):
        """Test support contact with message too short"""
        response = requests.post(f"{BASE_URL}/api/recovery/support-contact", json={
            "email": "test@example.com",
            "subject": "Test",
            "phone_number": "+5511999999999",
            "message": "Hi"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "10" in data["detail"]
    
    def test_support_contact_exactly_200_chars(self):
        """Test support contact with exactly 200 characters (should succeed)"""
        message_200 = "A" * 200
        response = requests.post(f"{BASE_URL}/api/recovery/support-contact", json={
            "email": "test@example.com",
            "subject": "Test 200 chars",
            "phone_number": "+5511999999999",
            "message": message_200
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
    
    def test_support_contact_missing_fields(self):
        """Test support contact with missing required fields"""
        response = requests.post(f"{BASE_URL}/api/recovery/support-contact", json={
            "email": "test@example.com"
        })
        
        assert response.status_code == 422
    
    def test_support_contact_invalid_email(self):
        """Test support contact with invalid email format"""
        response = requests.post(f"{BASE_URL}/api/recovery/support-contact", json={
            "email": "invalid-email",
            "subject": "Test",
            "phone_number": "+5511999999999",
            "message": "This is a test message for support"
        })
        
        assert response.status_code == 422


class TestFullRecoveryFlow:
    """Integration test for the complete 3-step recovery flow"""
    
    def test_full_recovery_flow_identity_verification(self):
        """Test Step 1: Identity verification creates recovery request"""
        response = requests.post(f"{BASE_URL}/api/recovery/verify-identity", json={
            "email": TEST_USER["email"],
            "full_name": TEST_USER["full_name"],
            "phone_number": TEST_USER["phone_number"],
            "cpf": TEST_USER["cpf"],
            "document_number": TEST_USER["document_number"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "email_masked" in data
        # Verify masked email format
        assert data["email_masked"].startswith("tes")
        assert "***" in data["email_masked"]
        assert "@ris.app" in data["email_masked"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
