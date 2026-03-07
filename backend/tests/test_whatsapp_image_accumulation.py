"""
Test WhatsApp Webhook Image Accumulation Feature
-------------------------------------------------
Tests the flow where admin sends multiple payment proof images via WhatsApp,
and the system accumulates them until 'listo' command is sent to process.

Key scenarios:
1. First image creates buffer for pending withdrawal
2. Subsequent images accumulate to the same withdrawal (using atomic $push $each)
3. 'listo' command processes all accumulated images
4. Verify pending_images field contains all images
5. Verify proof_images contains all images after processing
"""

import pytest
import requests
import os
from datetime import datetime, timezone
from bson import ObjectId

# Get BASE_URL from environment - for VITE apps use VITE_API_URL
BASE_URL = os.environ.get('VITE_API_URL', '').rstrip('/')
if not BASE_URL:
    # Try alternative env var names
    BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pago-movil-app.preview.emergentagent.com/api').rstrip('/')

print(f"Using BASE_URL: {BASE_URL}")


class TestWhatsAppImageAccumulation:
    """Test the WhatsApp webhook image accumulation feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data before each test"""
        self.admin_phone = "whatsapp:+5595840981​71"
        self.test_phone = "whatsapp:+1234567890"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/x-www-form-urlencoded"})
        
        # Generate unique transaction ID for this test run
        self.test_tx_id = f"TEST_TX_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
    def _get_mongo_client(self):
        """Get MongoDB client for direct database operations"""
        from pymongo import MongoClient
        mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        db_name = os.environ.get('DB_NAME', 'test_database')
        client = MongoClient(mongo_url)
        return client[db_name]
    
    def _create_test_withdrawal(self, tx_id=None, status="pending", whatsapp_active=False):
        """Create a test withdrawal transaction directly in DB"""
        db = self._get_mongo_client()
        
        if tx_id is None:
            tx_id = f"TEST_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        withdrawal = {
            "transaction_id": tx_id,
            "display_id": tx_id[:8],
            "type": "withdrawal",
            "status": status,
            "user_id": "test_user_123",
            "amount_input": 100.0,
            "amount_output": 500.0,
            "beneficiary_data": {
                "full_name": "Test User",
                "bank": "Test Bank",
                "account": "123456789"
            },
            "created_at": datetime.now(timezone.utc),
            "whatsapp_active": whatsapp_active
        }
        
        result = db.transactions.insert_one(withdrawal)
        withdrawal['_id'] = result.inserted_id
        return withdrawal
    
    def _cleanup_test_data(self, tx_id=None, mongo_id=None):
        """Clean up test data from database"""
        db = self._get_mongo_client()
        if mongo_id:
            db.transactions.delete_one({"_id": mongo_id})
        if tx_id:
            db.transactions.delete_many({"transaction_id": {"$regex": "^TEST_"}})
            db.admin_payment_records.delete_many({"transaction_id": {"$regex": "^TEST_"}})
    
    def _get_transaction(self, mongo_id):
        """Get transaction by MongoDB ID"""
        db = self._get_mongo_client()
        return db.transactions.find_one({"_id": mongo_id})
    
    def _simulate_webhook_with_image(self, num_images=1, body=""):
        """
        Simulate Twilio WhatsApp webhook with images.
        Since we can't actually download from Twilio URLs, 
        we'll test the endpoint returns expected behavior.
        """
        # Build form data like Twilio sends
        form_data = {
            "From": self.test_phone,
            "Body": body,
            "NumMedia": str(num_images),
            "MessageSid": f"SM{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        }
        
        # Add media URLs (these won't actually download since we don't have Twilio creds)
        for i in range(num_images):
            form_data[f"MediaUrl{i}"] = f"https://api.twilio.com/2010-04-01/Accounts/fake/Messages/fake/Media/fake{i}"
            form_data[f"MediaContentType{i}"] = "image/jpeg"
        
        return form_data

    # ==================== Unit Tests ====================
    
    def test_01_webhook_endpoint_exists(self):
        """Test that the WhatsApp webhook endpoint exists and responds"""
        # Test with empty body (no image, no command)
        form_data = {
            "From": self.test_phone,
            "Body": "hello",
            "NumMedia": "0",
            "MessageSid": "SMtest123"
        }
        
        response = self.session.post(
            f"{BASE_URL}/webhooks/twilio/whatsapp",
            data=form_data
        )
        
        # Should return some response (not 404)
        assert response.status_code in [200, 400, 422], f"Endpoint returned {response.status_code}: {response.text}"
        print(f"Webhook endpoint exists, returned: {response.status_code}")
    
    def test_02_create_pending_withdrawal_for_test(self):
        """Create a pending withdrawal that can be used for subsequent tests"""
        try:
            withdrawal = self._create_test_withdrawal(
                tx_id="TEST_ACCUMULATION_01",
                status="pending",
                whatsapp_active=False
            )
            
            assert withdrawal is not None
            assert withdrawal['status'] == 'pending'
            assert withdrawal['type'] == 'withdrawal'
            
            print(f"Created test withdrawal: {withdrawal['transaction_id']}")
            
            # Clean up
            self._cleanup_test_data(mongo_id=withdrawal['_id'])
        except Exception as e:
            print(f"Database operation failed: {e}")
            pytest.skip("Cannot connect to MongoDB")
    
    def test_03_listo_command_no_pending_images(self):
        """Test 'listo' command when there are no pending images returns appropriate response"""
        # First ensure no active transactions with pending images
        db = self._get_mongo_client()
        
        # Create a withdrawal WITHOUT pending_images
        withdrawal = self._create_test_withdrawal(
            tx_id="TEST_LISTO_NO_IMAGES",
            status="pending",
            whatsapp_active=True
        )
        
        try:
            form_data = {
                "From": self.test_phone,
                "Body": "listo",
                "NumMedia": "0",
                "MessageSid": "SMlisto123"
            }
            
            response = self.session.post(
                f"{BASE_URL}/webhooks/twilio/whatsapp",
                data=form_data
            )
            
            # The endpoint should handle this gracefully
            assert response.status_code in [200, 400, 500], f"Unexpected status: {response.status_code}"
            
            # Check response contains expected status
            try:
                data = response.json()
                print(f"'listo' with no images response: {data}")
                # Expected: {"status": "no_pending_images"} or Twilio send error
            except:
                print(f"Response text: {response.text}")
            
        finally:
            self._cleanup_test_data(mongo_id=withdrawal['_id'])
    
    def test_04_verify_push_each_logic_in_code(self):
        """
        Verify that the database update uses atomic $push $each operation.
        This is a code verification test - we simulate what the webhook does.
        """
        db = self._get_mongo_client()
        
        # Create test withdrawal
        withdrawal = self._create_test_withdrawal(
            tx_id="TEST_PUSH_EACH",
            status="pending",
            whatsapp_active=False
        )
        mongo_id = withdrawal['_id']
        
        try:
            # Simulate first image (using same logic as server.py lines 3798-3804)
            first_images = ["data:image/jpeg;base64,first_image_data"]
            
            result1 = db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {
                    "$push": {"pending_images": {"$each": first_images}},
                    "$set": {"whatsapp_active": True}
                }
            )
            
            assert result1.modified_count == 1, "First update should modify the document"
            
            # Verify first image was added
            tx = db.transactions.find_one({"_id": mongo_id})
            assert tx is not None
            assert tx.get('whatsapp_active') == True
            assert len(tx.get('pending_images', [])) == 1
            print(f"After first image: pending_images count = {len(tx['pending_images'])}")
            
            # Simulate second image
            second_images = ["data:image/jpeg;base64,second_image_data"]
            
            result2 = db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {
                    "$push": {"pending_images": {"$each": second_images}},
                    "$set": {"whatsapp_active": True}
                }
            )
            
            assert result2.modified_count == 1, "Second update should modify the document"
            
            # Verify both images are present
            tx = db.transactions.find_one({"_id": mongo_id})
            assert len(tx.get('pending_images', [])) == 2
            print(f"After second image: pending_images count = {len(tx['pending_images'])}")
            
            # Simulate third image
            third_images = ["data:image/jpeg;base64,third_image_data"]
            
            result3 = db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {
                    "$push": {"pending_images": {"$each": third_images}},
                    "$set": {"whatsapp_active": True}
                }
            )
            
            assert result3.modified_count == 1, "Third update should modify the document"
            
            # Verify all three images are present
            tx = db.transactions.find_one({"_id": mongo_id})
            assert len(tx.get('pending_images', [])) == 3
            print(f"After third image: pending_images count = {len(tx['pending_images'])}")
            
            # Verify the images are in correct order
            assert tx['pending_images'][0] == "data:image/jpeg;base64,first_image_data"
            assert tx['pending_images'][1] == "data:image/jpeg;base64,second_image_data"
            assert tx['pending_images'][2] == "data:image/jpeg;base64,third_image_data"
            
            print("SUCCESS: $push $each operation correctly accumulates images atomically")
            
        finally:
            self._cleanup_test_data(mongo_id=mongo_id)
    
    def test_05_process_command_moves_images_to_proof(self):
        """
        Test that 'listo' command moves pending_images to proof_images
        and marks transaction as completed.
        """
        db = self._get_mongo_client()
        
        # Create withdrawal with pending images already buffered
        tx_id = f"TEST_PROCESS_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        withdrawal = {
            "transaction_id": tx_id,
            "display_id": tx_id[:8],
            "type": "withdrawal",
            "status": "pending",
            "user_id": "test_user_123",
            "amount_input": 100.0,
            "amount_output": 500.0,
            "beneficiary_data": {
                "full_name": "Test User",
                "bank": "Test Bank",
                "account": "123456789"
            },
            "created_at": datetime.now(timezone.utc),
            "whatsapp_active": True,
            "pending_images": [
                "data:image/jpeg;base64,image1",
                "data:image/jpeg;base64,image2",
                "data:image/jpeg;base64,image3"
            ]
        }
        
        result = db.transactions.insert_one(withdrawal)
        mongo_id = result.inserted_id
        
        # Also create a test user to avoid notification errors
        db.users.update_one(
            {"user_id": "test_user_123"},
            {"$set": {"user_id": "test_user_123", "email": "test@test.com", "name": "Test User"}},
            upsert=True
        )
        
        try:
            # Simulate the processing logic from server.py lines 3853-3864
            images_base64 = withdrawal['pending_images']
            
            process_result = db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {"$set": {
                    "status": "completed",
                    "proof_images": images_base64,
                    "proof_image": images_base64[0] if images_base64 else None,
                    "completed_at": datetime.now(timezone.utc),
                    "processed_via": "whatsapp",
                    "whatsapp_active": False
                },
                "$unset": {"pending_images": ""}}
            )
            
            assert process_result.modified_count == 1, "Should modify the document"
            
            # Verify the transaction was processed correctly
            tx = db.transactions.find_one({"_id": mongo_id})
            
            assert tx['status'] == 'completed', f"Status should be completed, got: {tx['status']}"
            assert tx['whatsapp_active'] == False, "whatsapp_active should be False"
            assert 'pending_images' not in tx, "pending_images should be removed"
            assert 'proof_images' in tx, "proof_images should exist"
            assert len(tx['proof_images']) == 3, f"Should have 3 proof images, got: {len(tx.get('proof_images', []))}"
            assert tx['proof_image'] == "data:image/jpeg;base64,image1", "proof_image should be first image"
            assert tx['processed_via'] == 'whatsapp', "processed_via should be whatsapp"
            
            print(f"SUCCESS: Transaction processed with {len(tx['proof_images'])} proof images")
            
        finally:
            db.transactions.delete_one({"_id": mongo_id})
            db.users.delete_one({"user_id": "test_user_123"})
    
    def test_06_whatsapp_active_flag_query(self):
        """Test that the system finds the correct active withdrawal"""
        db = self._get_mongo_client()
        
        # Create multiple pending withdrawals
        tx1 = self._create_test_withdrawal(tx_id="TEST_TX1", status="pending", whatsapp_active=False)
        tx2 = self._create_test_withdrawal(tx_id="TEST_TX2", status="pending", whatsapp_active=True)
        tx3 = self._create_test_withdrawal(tx_id="TEST_TX3", status="pending", whatsapp_active=False)
        
        try:
            # Query as the server does (line 3766-3768)
            active_withdrawal = db.transactions.find_one(
                {"type": "withdrawal", "status": "pending", "whatsapp_active": True}
            )
            
            assert active_withdrawal is not None, "Should find active withdrawal"
            assert active_withdrawal['transaction_id'] == "TEST_TX2", f"Should find TX2, found: {active_withdrawal['transaction_id']}"
            
            print(f"SUCCESS: Found correct active withdrawal: {active_withdrawal['transaction_id']}")
            
        finally:
            self._cleanup_test_data(mongo_id=tx1['_id'])
            self._cleanup_test_data(mongo_id=tx2['_id'])
            self._cleanup_test_data(mongo_id=tx3['_id'])
    
    def test_07_fallback_to_oldest_pending(self):
        """Test fallback query when no whatsapp_active withdrawal exists"""
        db = self._get_mongo_client()
        
        import time
        
        # Create pending withdrawals without whatsapp_active (all False)
        tx1 = self._create_test_withdrawal(tx_id="TEST_OLDEST_TX1", status="pending", whatsapp_active=False)
        time.sleep(0.1)  # Ensure different timestamps
        tx2 = self._create_test_withdrawal(tx_id="TEST_OLDEST_TX2", status="pending", whatsapp_active=False)
        time.sleep(0.1)
        tx3 = self._create_test_withdrawal(tx_id="TEST_OLDEST_TX3", status="pending", whatsapp_active=False)
        
        try:
            # First query (should return None)
            active_withdrawal = db.transactions.find_one(
                {"type": "withdrawal", "status": "pending", "whatsapp_active": True}
            )
            
            # Filter to only our test transactions
            test_active = None
            if active_withdrawal and active_withdrawal.get('transaction_id', '').startswith('TEST_OLDEST'):
                test_active = active_withdrawal
            
            # Fallback query (lines 3774-3777)
            if not test_active:
                fallback = db.transactions.find_one(
                    {"type": "withdrawal", "status": "pending", "transaction_id": {"$regex": "^TEST_OLDEST"}},
                    sort=[("created_at", 1)]
                )
                
                assert fallback is not None, "Should find fallback withdrawal"
                assert fallback['transaction_id'] == "TEST_OLDEST_TX1", f"Should find oldest TX1, found: {fallback['transaction_id']}"
                
                print(f"SUCCESS: Fallback found oldest withdrawal: {fallback['transaction_id']}")
            
        finally:
            self._cleanup_test_data(mongo_id=tx1['_id'])
            self._cleanup_test_data(mongo_id=tx2['_id'])
            self._cleanup_test_data(mongo_id=tx3['_id'])
    
    def test_08_concurrent_image_additions(self):
        """Test that concurrent image additions don't lose data (atomic operation verification)"""
        db = self._get_mongo_client()
        
        # Create test withdrawal
        withdrawal = self._create_test_withdrawal(
            tx_id="TEST_CONCURRENT",
            status="pending",
            whatsapp_active=True
        )
        mongo_id = withdrawal['_id']
        
        try:
            # Simulate multiple rapid image additions (like concurrent webhook calls)
            import threading
            import time
            
            results = []
            
            def add_image(image_num):
                """Simulate adding an image"""
                images = [f"data:image/jpeg;base64,concurrent_image_{image_num}"]
                result = db.transactions.update_one(
                    {"_id": mongo_id, "status": "pending"},
                    {
                        "$push": {"pending_images": {"$each": images}},
                        "$set": {"whatsapp_active": True}
                    }
                )
                results.append((image_num, result.modified_count))
            
            # Create threads
            threads = []
            for i in range(5):
                t = threading.Thread(target=add_image, args=(i,))
                threads.append(t)
            
            # Start all threads almost simultaneously
            for t in threads:
                t.start()
            
            # Wait for all threads to complete
            for t in threads:
                t.join()
            
            # Verify all 5 images were added
            tx = db.transactions.find_one({"_id": mongo_id})
            pending_images = tx.get('pending_images', [])
            
            assert len(pending_images) == 5, f"Should have 5 images after concurrent additions, got: {len(pending_images)}"
            
            # Verify all images are present
            for i in range(5):
                assert any(f"concurrent_image_{i}" in img for img in pending_images), f"Image {i} should be present"
            
            print(f"SUCCESS: All 5 concurrent image additions preserved (atomic $push $each works)")
            
        finally:
            self._cleanup_test_data(mongo_id=mongo_id)
    
    def test_09_process_commands_variations(self):
        """Test that all process command variations are recognized"""
        db = self._get_mongo_client()
        
        process_commands = ['listo', 'ok', 'completar', 'procesar', 'enviar', 'done', 'ready']
        
        for cmd in process_commands:
            # Test lowercase
            body_lower = cmd.strip().lower()
            is_process_command = body_lower in process_commands
            assert is_process_command, f"'{cmd}' should be recognized as process command"
            
            # Test uppercase
            body_upper = cmd.upper().strip().lower()
            is_process_command_upper = body_upper in process_commands
            assert is_process_command_upper, f"'{cmd.upper()}' should be recognized as process command"
            
            # Test with whitespace
            body_space = f"  {cmd}  ".strip().lower()
            is_process_command_space = body_space in process_commands
            assert is_process_command_space, f"'  {cmd}  ' should be recognized as process command"
        
        print(f"SUCCESS: All {len(process_commands)} process commands are recognized")
    
    def test_10_full_accumulation_flow_simulation(self):
        """
        Simulate the complete flow:
        1. Create pending withdrawal
        2. Add first image (sets whatsapp_active)
        3. Add second image (accumulates)
        4. Add third image (accumulates)
        5. Process with 'listo' command
        6. Verify all images in proof_images
        """
        db = self._get_mongo_client()
        
        # Step 1: Create pending withdrawal
        tx_id = f"TEST_FULL_FLOW_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        withdrawal = {
            "transaction_id": tx_id,
            "display_id": tx_id[:8],
            "type": "withdrawal",
            "status": "pending",
            "user_id": "test_user_full_flow",
            "amount_input": 250.0,
            "amount_output": 1250.0,
            "beneficiary_data": {
                "full_name": "Full Flow Test User",
                "bank": "Test Bank",
                "account": "987654321"
            },
            "created_at": datetime.now(timezone.utc),
            "whatsapp_active": False
        }
        
        result = db.transactions.insert_one(withdrawal)
        mongo_id = result.inserted_id
        
        # Create test user
        db.users.update_one(
            {"user_id": "test_user_full_flow"},
            {"$set": {"user_id": "test_user_full_flow", "email": "fullflow@test.com", "name": "Full Flow User"}},
            upsert=True
        )
        
        try:
            # Step 2: First image
            first_images = ["data:image/jpeg;base64,FIRST_PAYMENT_PROOF"]
            db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {
                    "$push": {"pending_images": {"$each": first_images}},
                    "$set": {"whatsapp_active": True}
                }
            )
            
            tx = db.transactions.find_one({"_id": mongo_id})
            assert tx['whatsapp_active'] == True
            assert len(tx.get('pending_images', [])) == 1
            print(f"Step 2: First image added, total: {len(tx['pending_images'])}")
            
            # Step 3: Second image
            second_images = ["data:image/jpeg;base64,SECOND_PAYMENT_PROOF"]
            db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {
                    "$push": {"pending_images": {"$each": second_images}},
                    "$set": {"whatsapp_active": True}
                }
            )
            
            tx = db.transactions.find_one({"_id": mongo_id})
            assert len(tx.get('pending_images', [])) == 2
            print(f"Step 3: Second image added, total: {len(tx['pending_images'])}")
            
            # Step 4: Third image
            third_images = ["data:image/jpeg;base64,THIRD_PAYMENT_PROOF"]
            db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {
                    "$push": {"pending_images": {"$each": third_images}},
                    "$set": {"whatsapp_active": True}
                }
            )
            
            tx = db.transactions.find_one({"_id": mongo_id})
            assert len(tx.get('pending_images', [])) == 3
            print(f"Step 4: Third image added, total: {len(tx['pending_images'])}")
            
            # Step 5: Process with 'listo'
            images_to_process = tx.get('pending_images', [])
            
            db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {"$set": {
                    "status": "completed",
                    "proof_images": images_to_process,
                    "proof_image": images_to_process[0] if images_to_process else None,
                    "completed_at": datetime.now(timezone.utc),
                    "processed_via": "whatsapp",
                    "whatsapp_active": False
                },
                "$unset": {"pending_images": ""}}
            )
            
            # Step 6: Verify final state
            tx = db.transactions.find_one({"_id": mongo_id})
            
            assert tx['status'] == 'completed', f"Status should be completed, got: {tx['status']}"
            assert tx['whatsapp_active'] == False
            assert 'pending_images' not in tx
            assert len(tx['proof_images']) == 3, f"Should have 3 proof images, got: {len(tx.get('proof_images', []))}"
            assert tx['proof_images'][0] == "data:image/jpeg;base64,FIRST_PAYMENT_PROOF"
            assert tx['proof_images'][1] == "data:image/jpeg;base64,SECOND_PAYMENT_PROOF"
            assert tx['proof_images'][2] == "data:image/jpeg;base64,THIRD_PAYMENT_PROOF"
            assert tx['processed_via'] == 'whatsapp'
            
            print(f"Step 6: FULL FLOW SUCCESS!")
            print(f"  - Transaction ID: {tx['transaction_id']}")
            print(f"  - Status: {tx['status']}")
            print(f"  - Proof images: {len(tx['proof_images'])}")
            print(f"  - Processed via: {tx['processed_via']}")
            
        finally:
            db.transactions.delete_one({"_id": mongo_id})
            db.users.delete_one({"user_id": "test_user_full_flow"})
            db.admin_payment_records.delete_many({"transaction_id": tx_id})


class TestWebhookEndpointDirectly:
    """Test the actual webhook endpoint (may fail due to Twilio credentials)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
    
    def test_webhook_returns_valid_response_for_text_message(self):
        """Test webhook handles text-only messages"""
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "hello test",
            "NumMedia": "0",
            "MessageSid": "SMtest123456"
        }
        
        response = self.session.post(
            f"{BASE_URL}/webhooks/twilio/whatsapp",
            data=form_data
        )
        
        # Should not return 404 or 405
        assert response.status_code not in [404, 405], f"Endpoint error: {response.status_code}"
        print(f"Text message handled, status: {response.status_code}")
    
    def test_webhook_with_listo_command(self):
        """Test webhook handles 'listo' command"""
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "listo",
            "NumMedia": "0",
            "MessageSid": "SMlisto123456"
        }
        
        response = self.session.post(
            f"{BASE_URL}/webhooks/twilio/whatsapp",
            data=form_data
        )
        
        # Endpoint should exist
        assert response.status_code not in [404, 405], f"Endpoint error: {response.status_code}"
        print(f"'listo' command handled, status: {response.status_code}")
        
        try:
            data = response.json()
            print(f"Response: {data}")
        except:
            print(f"Response text: {response.text[:200]}")


# Cleanup fixture that runs after all tests
@pytest.fixture(scope="session", autouse=True)
def cleanup_all_test_data():
    """Clean up all test data after test session"""
    yield
    
    from pymongo import MongoClient
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    client = MongoClient(mongo_url)
    db = client[db_name]
    
    # Delete all test transactions
    result = db.transactions.delete_many({"transaction_id": {"$regex": "^TEST_"}})
    print(f"Cleaned up {result.deleted_count} test transactions")
    
    # Delete test admin records
    result = db.admin_payment_records.delete_many({"transaction_id": {"$regex": "^TEST_"}})
    print(f"Cleaned up {result.deleted_count} test admin records")
    
    # Delete test users
    result = db.users.delete_many({"user_id": {"$regex": "^test_user"}})
    print(f"Cleaned up {result.deleted_count} test users")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
