"""
KYC Admin Backend API Tests
Tests all endpoints for the enhanced KYC management system.
"""
import requests
import sys
from datetime import datetime

class KycAdminTester:
    def __init__(self, base_url="https://teamwork-platform-2.preview.emergentagent.com/api"):
        self.base_url = base_url
        # Pre-issued session token for admin bypass (valid 7d)
        self.session_token = "REDACTED"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.session_token}'
        }

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except:
                    print(f"   Response: {response.text[:200]}")
                self.failed_tests.append({
                    'name': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'endpoint': endpoint
                })
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                'name': name,
                'error': str(e),
                'endpoint': endpoint
            })
            return False, {}

    def test_list_kyc_pending(self):
        """Test GET /admin/kyc/list?status=pending with counts"""
        success, response = self.run_test(
            "List KYC - Pending",
            "GET",
            "admin/kyc/list",
            200,
            params={"status": "pending"}
        )
        if success:
            # Verify response structure
            if 'counts' in response and 'items' in response:
                print(f"   Counts: {response['counts']}")
                print(f"   Items: {len(response['items'])} pending verifications")
                return response
            else:
                print(f"   ⚠️  Missing 'counts' or 'items' in response")
        return None

    def test_list_kyc_approved(self):
        """Test GET /admin/kyc/list?status=approved"""
        success, response = self.run_test(
            "List KYC - Approved",
            "GET",
            "admin/kyc/list",
            200,
            params={"status": "approved"}
        )
        if success:
            print(f"   Approved items: {len(response.get('items', []))}")
        return response if success else None

    def test_list_kyc_rejected(self):
        """Test GET /admin/kyc/list?status=rejected"""
        success, response = self.run_test(
            "List KYC - Rejected",
            "GET",
            "admin/kyc/list",
            200,
            params={"status": "rejected"}
        )
        if success:
            print(f"   Rejected items: {len(response.get('items', []))}")
        return response if success else None

    def test_list_kyc_all(self):
        """Test GET /admin/kyc/list?status=all"""
        success, response = self.run_test(
            "List KYC - All",
            "GET",
            "admin/kyc/list",
            200,
            params={"status": "all"}
        )
        if success:
            print(f"   Total items: {len(response.get('items', []))}")
        return response if success else None

    def test_search_kyc(self):
        """Test GET /admin/kyc/list?search=joao (search by name/email/CPF)"""
        success, response = self.run_test(
            "Search KYC - 'joao'",
            "GET",
            "admin/kyc/list",
            200,
            params={"status": "all", "search": "joao"}
        )
        if success:
            print(f"   Search results: {len(response.get('items', []))} items")
            if response.get('items'):
                print(f"   First result: {response['items'][0].get('full_name', 'N/A')}")
        return response if success else None

    def test_rejection_reasons(self):
        """Test GET /admin/kyc/rejection-reasons"""
        success, response = self.run_test(
            "Get Rejection Reasons",
            "GET",
            "admin/kyc/rejection-reasons",
            200
        )
        if success:
            if isinstance(response, list) and len(response) == 6:
                print(f"   ✅ Got 6 predefined reasons")
                for r in response:
                    print(f"      - {r.get('code')}: {r.get('label')}")
            else:
                print(f"   ⚠️  Expected 6 reasons, got {len(response) if isinstance(response, list) else 'invalid'}")
        return response if success else None

    def test_approve_kyc(self, verification_id):
        """Test POST /admin/kyc/{id}/approve"""
        if not verification_id:
            print("⚠️  Skipping approve test - no verification_id")
            return None
        
        success, response = self.run_test(
            f"Approve KYC - {verification_id[:8]}",
            "POST",
            f"admin/kyc/{verification_id}/approve",
            200
        )
        if success:
            print(f"   Message: {response.get('message', 'N/A')}")
        return response if success else None

    def test_reject_kyc_without_text(self, verification_id):
        """Test POST /admin/kyc/{id}/reject with reason_code='other' WITHOUT reason_text (should fail 400)"""
        if not verification_id:
            print("⚠️  Skipping reject test - no verification_id")
            return None
        
        success, response = self.run_test(
            f"Reject KYC - 'other' without text (should fail)",
            "POST",
            f"admin/kyc/{verification_id}/reject",
            400,  # Expecting 400 error
            data={"reason_code": "other", "reason_text": ""}
        )
        if success:
            print(f"   ✅ Correctly rejected with 400")
        return response if success else None

    def test_reject_kyc_with_text(self, verification_id):
        """Test POST /admin/kyc/{id}/reject with reason_code='other' WITH reason_text"""
        if not verification_id:
            print("⚠️  Skipping reject test - no verification_id")
            return None
        
        success, response = self.run_test(
            f"Reject KYC - 'other' with text",
            "POST",
            f"admin/kyc/{verification_id}/reject",
            200,
            data={"reason_code": "other", "reason_text": "Documento no cumple con los requisitos"}
        )
        if success:
            print(f"   Message: {response.get('message', 'N/A')}")
            print(f"   Reason: {response.get('reason', 'N/A')}")
        return response if success else None

    def test_reject_kyc_predefined(self, verification_id):
        """Test POST /admin/kyc/{id}/reject with predefined reason"""
        if not verification_id:
            print("⚠️  Skipping reject test - no verification_id")
            return None
        
        success, response = self.run_test(
            f"Reject KYC - predefined reason",
            "POST",
            f"admin/kyc/{verification_id}/reject",
            200,
            data={"reason_code": "illegible", "reason_text": ""}
        )
        if success:
            print(f"   Message: {response.get('message', 'N/A')}")
        return response if success else None

    def test_update_note(self, verification_id):
        """Test PATCH /admin/kyc/{id}/note"""
        if not verification_id:
            print("⚠️  Skipping note test - no verification_id")
            return None
        
        success, response = self.run_test(
            f"Update Admin Note - {verification_id[:8]}",
            "PATCH",
            f"admin/kyc/{verification_id}/note",
            200,
            data={"note": f"Test note added at {datetime.now().isoformat()}"}
        )
        if success:
            print(f"   Note saved: {response.get('note', 'N/A')[:50]}...")
        return response if success else None

    def test_get_history(self, verification_id):
        """Test GET /admin/kyc/{id}/history"""
        if not verification_id:
            print("⚠️  Skipping history test - no verification_id")
            return None
        
        success, response = self.run_test(
            f"Get Audit History - {verification_id[:8]}",
            "GET",
            f"admin/kyc/{verification_id}/history",
            200
        )
        if success:
            history = response.get('history', [])
            print(f"   History entries: {len(history)}")
            if history:
                print(f"   Latest action: {history[0].get('action', 'N/A')} by {history[0].get('admin_name', 'N/A')}")
        return response if success else None

    def test_auth_required(self):
        """Test that endpoints require super_admin auth (401/403 without token)"""
        url = f"{self.base_url}/admin/kyc/list"
        headers = {'Content-Type': 'application/json'}  # No auth token
        
        self.tests_run += 1
        print(f"\n🔍 Testing Auth Required (no token)...")
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code in [401, 403]:
                self.tests_passed += 1
                print(f"✅ Passed - Correctly rejected with {response.status_code}")
                return True
            else:
                print(f"❌ Failed - Expected 401/403, got {response.status_code}")
                self.failed_tests.append({
                    'name': 'Auth Required',
                    'expected': '401 or 403',
                    'actual': response.status_code
                })
                return False
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False

    def test_selfie_image_bug(self, pending_list):
        """Test critical bug: selfie images should NOT be 'data:,' (empty)"""
        print(f"\n🔍 Testing Selfie Image Bug Fix...")
        self.tests_run += 1
        
        if not pending_list or not pending_list.get('items'):
            print("⚠️  No pending items to check")
            return None
        
        items_with_selfie = 0
        items_with_empty_selfie = 0
        
        for item in pending_list['items']:
            selfie = item.get('selfie_image')
            if selfie:
                items_with_selfie += 1
                if selfie in ['data:', 'data:,', 'null', 'undefined'] or len(selfie) < 30:
                    items_with_empty_selfie += 1
                    print(f"   ❌ Empty selfie found for {item.get('full_name', 'N/A')}: '{selfie}'")
        
        if items_with_empty_selfie == 0 and items_with_selfie > 0:
            self.tests_passed += 1
            print(f"   ✅ All {items_with_selfie} selfies are valid (not empty)")
            return True
        elif items_with_selfie == 0:
            print(f"   ⚠️  No selfie images found in pending items")
            return None
        else:
            print(f"   ❌ Found {items_with_empty_selfie} empty selfies out of {items_with_selfie}")
            self.failed_tests.append({
                'name': 'Selfie Image Bug',
                'issue': f'{items_with_empty_selfie} empty selfies found'
            })
            return False


def main():
    print("=" * 60)
    print("KYC Admin Backend API Tests")
    print("=" * 60)
    
    tester = KycAdminTester()
    
    # Test 1: Auth required
    tester.test_auth_required()
    
    # Test 2-5: List endpoints with different statuses
    pending_list = tester.test_list_kyc_pending()
    tester.test_list_kyc_approved()
    tester.test_list_kyc_rejected()
    tester.test_list_kyc_all()
    
    # Test 6: Search functionality
    tester.test_search_kyc()
    
    # Test 7: Rejection reasons
    tester.test_rejection_reasons()
    
    # Test 8: Critical bug - selfie images
    tester.test_selfie_image_bug(pending_list)
    
    # Get a verification_id for further tests
    verification_id = None
    if pending_list and pending_list.get('items'):
        verification_id = pending_list['items'][0].get('verification_id')
        print(f"\n📝 Using verification_id for tests: {verification_id}")
    
    # Test 9: Update note
    tester.test_update_note(verification_id)
    
    # Test 10: Get history
    tester.test_get_history(verification_id)
    
    # Test 11-13: Reject scenarios (only if we have a pending verification)
    # Note: These will modify data, so we test them last
    if verification_id:
        print("\n⚠️  Skipping approve/reject tests to preserve test data")
        print("   (These would modify the verification status)")
        # Uncomment to test:
        # tester.test_reject_kyc_without_text(verification_id)
        # tester.test_reject_kyc_with_text(verification_id)
        # tester.test_approve_kyc(verification_id)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print(f"Tests run: {tester.tests_run}")
    print(f"Tests passed: {tester.tests_passed}")
    print(f"Tests failed: {len(tester.failed_tests)}")
    
    if tester.failed_tests:
        print("\n❌ Failed Tests:")
        for fail in tester.failed_tests:
            print(f"   - {fail.get('name', 'Unknown')}")
            if 'expected' in fail:
                print(f"     Expected: {fail['expected']}, Got: {fail['actual']}")
            if 'error' in fail:
                print(f"     Error: {fail['error']}")
            if 'issue' in fail:
                print(f"     Issue: {fail['issue']}")
    
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"\n✅ Success Rate: {success_rate:.1f}%")
    
    return 0 if len(tester.failed_tests) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
