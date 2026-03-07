"""
Test Suite: Gestor WhatsApp Integration E2E Tests
Tests the complete flow of gestor transactions entering the FIFO WhatsApp queue
and being visible in admin panel with all required fields.
"""

import pytest
import requests
import os

# Load env from frontend since that has the public URL
from dotenv import load_dotenv
load_dotenv('/app/frontend/.env')

BASE_URL = os.environ.get('VITE_API_URL', '').rstrip('/')

# Test credentials
SUPER_ADMIN_EMAIL = "marshalljulio46@gmail.com"
SUPER_ADMIN_PASSWORD = "Admin2025!"
GESTOR_EMAIL = "testgestor@test.com"
GESTOR_PASSWORD = "Gestor2025!"


class TestGestorWhatsAppIntegration:
    """E2E tests for Gestor transactions with WhatsApp FIFO queue integration"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as super admin and return session with token"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/auth/login-password", json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
        
        data = response.json()
        session.headers.update({"Authorization": f"Bearer {data['session_token']}"})
        return session
    
    @pytest.fixture(scope="class")
    def gestor_session(self):
        """Login as gestor and return session with token"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/auth/login-password", json={
            "email": GESTOR_EMAIL,
            "password": GESTOR_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Gestor login failed: {response.status_code} - {response.text}")
        
        data = response.json()
        session.headers.update({"Authorization": f"Bearer {data['session_token']}"})
        return session

    # ===== EXISTING DATA VERIFICATION =====
    
    def test_existing_gestor_transactions_in_withdrawals(self, admin_session):
        """Verify existing gestor transactions (000001, 000002) appear in admin withdrawals"""
        response = admin_session.get(f"{BASE_URL}/admin/withdrawals/all")
        
        assert response.status_code == 200, f"Failed to get withdrawals: {response.text}"
        withdrawals = response.json()
        
        # Find gestor transactions
        gestor_withdrawals = [w for w in withdrawals if w.get('is_gestor_transaction') == True]
        
        assert len(gestor_withdrawals) >= 2, f"Expected at least 2 gestor transactions, found {len(gestor_withdrawals)}"
        print(f"✅ Found {len(gestor_withdrawals)} gestor transactions in admin withdrawals")
        
        # Verify display_ids
        display_ids = [w.get('display_id') for w in gestor_withdrawals]
        assert '000001' in display_ids, "Transaction 000001 not found"
        assert '000002' in display_ids, "Transaction 000002 not found"
        print(f"✅ Found transactions with display_ids: {display_ids}")

    def test_gestor_transaction_has_is_gestor_flag(self, admin_session):
        """Verify gestor transactions have is_gestor_transaction=true"""
        response = admin_session.get(f"{BASE_URL}/admin/withdrawals/all")
        
        assert response.status_code == 200
        withdrawals = response.json()
        
        # Find transaction 000001
        tx_000001 = next((w for w in withdrawals if w.get('display_id') == '000001'), None)
        assert tx_000001 is not None, "Transaction 000001 not found"
        
        assert tx_000001.get('is_gestor_transaction') == True, \
            f"Expected is_gestor_transaction=true, got {tx_000001.get('is_gestor_transaction')}"
        print(f"✅ Transaction 000001 has is_gestor_transaction=True")

    def test_gestor_transaction_has_payment_type(self, admin_session):
        """Verify gestor transactions have payment_type (pago_movil or transferencia)"""
        response = admin_session.get(f"{BASE_URL}/admin/withdrawals/all")
        
        assert response.status_code == 200
        withdrawals = response.json()
        
        # Find transactions
        tx_000001 = next((w for w in withdrawals if w.get('display_id') == '000001'), None)
        tx_000002 = next((w for w in withdrawals if w.get('display_id') == '000002'), None)
        
        assert tx_000001 is not None, "Transaction 000001 not found"
        assert tx_000002 is not None, "Transaction 000002 not found"
        
        # Verify payment types
        assert tx_000001.get('payment_type') == 'pago_movil', \
            f"Expected payment_type=pago_movil for 000001, got {tx_000001.get('payment_type')}"
        print(f"✅ Transaction 000001 has payment_type=pago_movil")
        
        assert tx_000002.get('payment_type') == 'transferencia', \
            f"Expected payment_type=transferencia for 000002, got {tx_000002.get('payment_type')}"
        print(f"✅ Transaction 000002 has payment_type=transferencia")

    def test_gestor_transaction_has_client_name(self, admin_session):
        """Verify gestor transactions have client_name from gestor"""
        response = admin_session.get(f"{BASE_URL}/admin/withdrawals/all")
        
        assert response.status_code == 200
        withdrawals = response.json()
        
        # Find transactions
        tx_000001 = next((w for w in withdrawals if w.get('display_id') == '000001'), None)
        tx_000002 = next((w for w in withdrawals if w.get('display_id') == '000002'), None)
        
        assert tx_000001 is not None, "Transaction 000001 not found"
        assert tx_000002 is not None, "Transaction 000002 not found"
        
        # Verify client names
        assert tx_000001.get('client_name') == 'Juan Cliente Test', \
            f"Expected client_name='Juan Cliente Test' for 000001, got {tx_000001.get('client_name')}"
        print(f"✅ Transaction 000001 has client_name='Juan Cliente Test'")
        
        assert tx_000002.get('client_name') == 'Maria Cliente Test', \
            f"Expected client_name='Maria Cliente Test' for 000002, got {tx_000002.get('client_name')}"
        print(f"✅ Transaction 000002 has client_name='Maria Cliente Test'")

    # ===== BALANCE VERIFICATION =====
    
    def test_gestor_balance_terceros_after_transactions(self, gestor_session):
        """Verify balance_ris_terceros was debited correctly (should be 350 RIS after 2 transactions)"""
        response = gestor_session.get(f"{BASE_URL}/gestor/dashboard")
        
        assert response.status_code == 200, f"Failed to get gestor dashboard: {response.text}"
        data = response.json()
        
        balance_terceros = data.get('balance_ris_terceros', 0)
        
        # Based on context: Started with some amount, after 50+100 RIS transactions = 350 remaining
        assert balance_terceros == 350.0, \
            f"Expected balance_ris_terceros=350.0, got {balance_terceros}"
        print(f"✅ Gestor balance_ris_terceros = {balance_terceros} RIS (correctly debited)")

    # ===== PENDING WITHDRAWALS QUEUE =====
    
    def test_pending_withdrawals_show_gestor_transactions(self, admin_session):
        """Verify pending withdrawals endpoint shows gestor transactions in FIFO order"""
        response = admin_session.get(f"{BASE_URL}/admin/withdrawals/pending")
        
        assert response.status_code == 200, f"Failed to get pending withdrawals: {response.text}"
        pending = response.json()
        
        # Should have gestor transactions in pending
        gestor_pending = [w for w in pending if w.get('is_gestor_transaction') == True]
        
        assert len(gestor_pending) >= 2, f"Expected at least 2 pending gestor transactions, found {len(gestor_pending)}"
        print(f"✅ Found {len(gestor_pending)} pending gestor transactions in queue")
        
        # Verify they have required fields
        for tx in gestor_pending:
            assert 'client_name' in tx, f"Missing client_name in {tx.get('display_id')}"
            assert 'payment_type' in tx, f"Missing payment_type in {tx.get('display_id')}"
            assert 'is_gestor_transaction' in tx, f"Missing is_gestor_transaction in {tx.get('display_id')}"
        
        print("✅ All pending gestor transactions have required fields")

    # ===== NEW TRANSACTION FLOW TEST =====
    
    def test_process_transaction_creates_withdrawal_in_queue(self, gestor_session, admin_session):
        """Test: POST /api/gestor/process-transaction creates withdrawal in FIFO queue"""
        # First, get current balance
        dashboard_resp = gestor_session.get(f"{BASE_URL}/gestor/dashboard")
        assert dashboard_resp.status_code == 200
        initial_balance = dashboard_resp.json().get('balance_ris_terceros', 0)
        
        # Check if we have enough balance for a test transaction
        test_amount = 10.0
        if initial_balance < test_amount:
            pytest.skip(f"Insufficient balance for test: {initial_balance} < {test_amount}")
        
        # Get a beneficiary
        bens_resp = gestor_session.get(f"{BASE_URL}/gestor/beneficiaries")
        assert bens_resp.status_code == 200
        beneficiaries = bens_resp.json()
        
        if not beneficiaries:
            pytest.skip("No beneficiaries available for testing")
        
        # Use pago_movil beneficiary for test
        pm_beneficiary = next((b for b in beneficiaries if b.get('payment_type') == 'pago_movil'), beneficiaries[0])
        
        # Create new transaction
        tx_response = gestor_session.post(f"{BASE_URL}/gestor/process-transaction", json={
            "amount_ris": test_amount,
            "beneficiary_id": pm_beneficiary['beneficiary_id'],
            "client_name": "TEST_E2E_Cliente",
            "payment_type": pm_beneficiary.get('payment_type', 'pago_movil'),
            "client_phone": "+5599999999"
        })
        
        assert tx_response.status_code == 200, f"Failed to create transaction: {tx_response.text}"
        tx_data = tx_response.json()
        
        print(f"✅ Created gestor transaction: {tx_data.get('display_id')}")
        
        # Verify balance was debited
        dashboard_after = gestor_session.get(f"{BASE_URL}/gestor/dashboard")
        assert dashboard_after.status_code == 200
        new_balance = dashboard_after.json().get('balance_ris_terceros', 0)
        
        assert new_balance == initial_balance - test_amount, \
            f"Balance not debited correctly: {initial_balance} - {test_amount} != {new_balance}"
        print(f"✅ Balance debited: {initial_balance} -> {new_balance}")
        
        # Verify transaction appears in admin withdrawals
        admin_withdrawals = admin_session.get(f"{BASE_URL}/admin/withdrawals/all")
        assert admin_withdrawals.status_code == 200
        
        all_withdrawals = admin_withdrawals.json()
        new_tx = next((w for w in all_withdrawals if w.get('display_id') == tx_data.get('display_id')), None)
        
        assert new_tx is not None, f"New transaction {tx_data.get('display_id')} not found in admin withdrawals"
        
        # Verify all required fields
        assert new_tx.get('is_gestor_transaction') == True, "New transaction missing is_gestor_transaction=true"
        assert new_tx.get('client_name') == "TEST_E2E_Cliente", f"Wrong client_name: {new_tx.get('client_name')}"
        assert new_tx.get('payment_type') in ['pago_movil', 'transferencia'], f"Invalid payment_type: {new_tx.get('payment_type')}"
        
        print(f"✅ New transaction verified in admin withdrawals with all fields")
        
        return tx_data.get('display_id')

    # ===== WHATSAPP NOTIFICATION FORMAT TEST =====
    
    def test_whatsapp_message_format_for_gestor(self):
        """Test: WhatsApp notification format includes Client and Gestor info
        
        Note: This is a code review test - we verify the send_next_pending_withdrawal_whatsapp 
        function builds correct message format for gestor transactions.
        
        Expected format for gestor transactions:
        - 👤 Cliente: {client_name}
        - 🏢 Gestor: {gestor_name}
        
        Expected format for regular transactions:
        - 👤 Usuario: {user_name}
        """
        # Read server.py to verify WhatsApp message format
        import re
        
        with open('/app/backend/server.py', 'r') as f:
            server_code = f.read()
        
        # Check for gestor-specific WhatsApp message format
        assert 'is_gestor = next_withdrawal.get(\'is_gestor_transaction\', False)' in server_code, \
            "Missing is_gestor check in WhatsApp function"
        
        assert 'client_name = next_withdrawal.get(\'client_name\', \'\')' in server_code, \
            "Missing client_name retrieval in WhatsApp function"
        
        # Check message format includes Cliente and Gestor for gestor transactions
        assert '👤 Cliente:' in server_code, "WhatsApp message missing '👤 Cliente:' format"
        assert '🏢 Gestor:' in server_code, "WhatsApp message missing '🏢 Gestor:' format"
        
        # Check conditional logic for user_info
        assert 'if is_gestor and client_name' in server_code, \
            "Missing conditional check for gestor message format"
        
        print("✅ WhatsApp notification format correctly includes Client and Gestor info")

    # ===== ADMIN PANEL DATA VERIFICATION =====
    
    def test_admin_withdrawals_all_returns_complete_data(self, admin_session):
        """Verify GET /api/admin/withdrawals/all returns all required fields for gestor transactions"""
        response = admin_session.get(f"{BASE_URL}/admin/withdrawals/all")
        
        assert response.status_code == 200
        withdrawals = response.json()
        
        # Find a gestor transaction
        gestor_tx = next((w for w in withdrawals if w.get('is_gestor_transaction') == True), None)
        
        if gestor_tx is None:
            pytest.skip("No gestor transactions found")
        
        # Verify all required fields exist
        required_fields = [
            'transaction_id',
            'display_id',
            'user_id',
            'user_name',
            'amount_input',
            'amount_output',
            'status',
            'beneficiary_data',
            'payment_type',
            'is_gestor_transaction',
            'client_name',
            'created_at'
        ]
        
        for field in required_fields:
            assert field in gestor_tx, f"Missing field '{field}' in gestor transaction"
        
        print(f"✅ Admin withdrawals endpoint returns all required fields for gestor transactions")
        print(f"   Sample transaction: display_id={gestor_tx.get('display_id')}, "
              f"is_gestor={gestor_tx.get('is_gestor_transaction')}, "
              f"client_name={gestor_tx.get('client_name')}, "
              f"payment_type={gestor_tx.get('payment_type')}")

    # ===== CLEANUP =====
    
    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, request):
        """Cleanup TEST_ prefixed data after tests"""
        yield
        # Cleanup is done by main agent or manually if needed


# Run tests when executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
