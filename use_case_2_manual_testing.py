#!/usr/bin/env python3
"""
🚨 USE CASE 2: Primary Instance Down - Manual Testing Protocol

CRITICAL: This test requires MANUAL primary instance suspension via Render dashboard.
DO NOT run this test without first suspending the primary instance.

This script has built-in safeguards to prevent accidental execution.
"""

import sys
import time
import requests
import json
import uuid
from datetime import datetime

class UseCase2ManualTester:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url
        self.test_session_id = f"USE_CASE_2_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.test_results = {}
        self.created_collections = set()
        self.created_documents = {}  # collection_name -> [doc_ids]
        
    def make_request(self, method, url, timeout=30, **kwargs):
        """Make HTTP request with error handling"""
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            return response
        except Exception as e:
            print(f"Request failed: {e}")
            return None

    def track_collection(self, collection_name):
        """Track collection for cleanup"""
        self.created_collections.add(collection_name)
        print(f"   📌 Tracking collection for cleanup: {collection_name}")

    def track_documents(self, collection_name, doc_ids):
        """Track documents for cleanup"""
        if collection_name not in self.created_documents:
            self.created_documents[collection_name] = []
        self.created_documents[collection_name].extend(doc_ids)
        print(f"   📌 Tracking {len(doc_ids)} documents for cleanup: {collection_name}")

    def check_system_health(self):
        """Check current system health"""
        print("\n🔍 Checking current system health...")
        
        response = self.make_request('GET', f"{self.base_url}/status")
        if not response or response.status_code != 200:
            print("❌ Cannot check system status")
            return False, False
            
        status = response.json()
        instances = status.get('instances', [])
        
        primary_healthy = any(inst.get('name') == 'primary' and inst.get('healthy') for inst in instances)
        replica_healthy = any(inst.get('name') == 'replica' and inst.get('healthy') for inst in instances)
        
        print(f"   Primary: {'✅ Healthy' if primary_healthy else '❌ Unhealthy'}")
        print(f"   Replica: {'✅ Healthy' if replica_healthy else '❌ Unhealthy'}")
        print(f"   Total Healthy: {status.get('healthy_instances', 0)}/{status.get('total_instances', 0)}")
        
        return primary_healthy, replica_healthy

    def require_manual_confirmation(self):
        """CRITICAL: Require explicit manual confirmation of primary suspension"""
        
        print("\n" + "="*80)
        print("🚨 USE CASE 2: PRIMARY INSTANCE DOWN - MANUAL TESTING PROTOCOL")
        print("="*80)
        
        print("\n⚠️  CRITICAL REQUIREMENT: MANUAL PRIMARY INSTANCE SUSPENSION")
        print("\nThis test simulates real infrastructure failure and requires:")
        print("1. 🖥️  Manual suspension of primary instance via Render dashboard")
        print("2. ⏳ Waiting 30-60 seconds for health detection") 
        print("3. 🧪 Testing CMS operations during actual failure")
        print("4. 🔄 Manual primary restoration and sync validation")
        
        print("\n🛡️  SAFEGUARD: This test will REFUSE to run if primary is still healthy")
        print("   (This prevents accidental execution without proper setup)")
        
        print("\n📋 MANUAL STEPS REQUIRED:")
        print("   1. Go to your Render dashboard")
        print("   2. Navigate to 'chroma-primary' service")
        print("   3. Click 'Suspend' to simulate infrastructure failure")
        print("   4. Wait 30-60 seconds for load balancer to detect failure")
        print("   5. THEN run this test script")
        
        print("\n" + "="*80)
        
        # First confirmation: Understanding the requirement
        response1 = input("\n❓ Do you understand this is a MANUAL testing protocol? (yes/no): ").strip().lower()
        if response1 != 'yes':
            print("\n❌ Test cancelled. Please read the requirements carefully.")
            return False
        
        # Second confirmation: Actual suspension
        response2 = input("\n❓ Have you ALREADY suspended the primary instance via Render dashboard? (yes/no): ").strip().lower()
        if response2 != 'yes':
            print("\n❌ Test cancelled. Please suspend the primary instance first.")
            print("   Go to Render dashboard → chroma-primary → Suspend")
            return False
        
        # Third confirmation: Timing
        response3 = input("\n❓ Have you waited 30-60 seconds for health detection? (yes/no): ").strip().lower()
        if response3 != 'yes':
            print("\n❌ Test cancelled. Please wait for health detection.")
            print("   Wait 30-60 seconds after suspending, then try again.")
            return False
        
        # Final confirmation with timestamp
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n📝 Recording manual confirmation at {current_time}")
        response4 = input("\n❓ Final confirmation - Start USE CASE 2 testing now? (yes/no): ").strip().lower()
        if response4 != 'yes':
            print("\n❌ Test cancelled by user.")
            return False
        
        return True

    def verify_primary_is_down(self):
        """CRITICAL SAFEGUARD: Verify primary is actually down before testing"""
        print("\n🔒 SAFEGUARD: Verifying primary instance is actually down...")
        
        primary_healthy, replica_healthy = self.check_system_health()
        
        if primary_healthy:
            print("\n🚨 CRITICAL ERROR: Primary instance is still healthy!")
            print("   This indicates the primary was NOT properly suspended.")
            print("\n🛑 REFUSING TO RUN TEST - Primary must be suspended first")
            print("\n📋 Required actions:")
            print("   1. Go to Render dashboard")
            print("   2. Find 'chroma-primary' service") 
            print("   3. Click 'Suspend' button")
            print("   4. Wait 30-60 seconds")
            print("   5. Re-run this test")
            return False
        
        if not replica_healthy:
            print("\n🚨 CRITICAL ERROR: Replica instance is also unhealthy!")
            print("   Cannot test failover without healthy replica.")
            print("\n🛑 REFUSING TO RUN TEST - Need healthy replica for failover testing")
            return False
        
        print("✅ SAFEGUARD PASSED: Primary down, replica healthy - Ready for failover testing")
        return True

    def run_use_case_2_testing(self):
        """Run the actual USE CASE 2 testing after all safeguards pass"""
        
        print("\n🚀 Starting USE CASE 2: Primary Instance Down Testing")
        print("="*60)
        
        # Test 1: CMS Upload Operations (should route to replica)
        print("\n🧪 Test 1: CMS Upload Operations During Primary Failure")
        collection_name = f"USE_CASE_2_test_upload_{int(time.time())}"
        
        create_response = self.make_request(
            'POST',
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            json={"name": collection_name},
            timeout=15
        )
        
        upload_success = create_response and create_response.status_code in [200, 201]
        print(f"   Upload Test: {'✅ Success' if upload_success else '❌ Failed'} ({create_response.status_code if create_response else 'No response'})")
        self.test_results["CMS Upload"] = upload_success
        
        if upload_success:
            self.track_collection(collection_name)
            
            # Test document addition
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["Test document during primary failure"],
                "metadatas": [{"test": "use_case_2", "scenario": "primary_down"}],
                "ids": ["test_doc_primary_down"]
            }
            
            doc_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data,
                timeout=15
            )
            
            doc_success = doc_response and doc_response.status_code in [200, 201]
            print(f"   Document Add: {'✅ Success' if doc_success else '❌ Failed'} ({doc_response.status_code if doc_response else 'No response'})")
            self.test_results["Document Add"] = doc_success
            
            if doc_success:
                self.track_documents(collection_name, ["test_doc_primary_down"])
        
        # Test 2: CMS Query Operations (should route to replica)
        print("\n🧪 Test 2: CMS Query Operations During Primary Failure")
        
        # Try to query the global collection (should exist)
        query_response = self.make_request(
            'POST',
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/global/query",
            json={"query_texts": ["test"], "n_results": 1},
            timeout=15
        )
        
        query_success = query_response and query_response.status_code == 200
        print(f"   Query Test: {'✅ Success' if query_success else '❌ Failed'} ({query_response.status_code if query_response else 'No response'})")
        self.test_results["CMS Query"] = query_success
        
        # Test 3: CMS Delete Operations (should route to replica)
        print("\n🧪 Test 3: CMS Delete Operations During Primary Failure")
        
        # Create a temporary collection for deletion test
        delete_test_collection = f"USE_CASE_2_delete_test_{int(time.time())}"
        
        delete_create_response = self.make_request(
            'POST',
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            json={"name": delete_test_collection},
            timeout=15
        )
        
        if delete_create_response and delete_create_response.status_code in [200, 201]:
            self.track_collection(delete_test_collection)
            time.sleep(2)  # Brief wait for creation
            
            delete_response = self.make_request(
                'DELETE',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{delete_test_collection}",
                timeout=15
            )
            
            delete_success = delete_response and delete_response.status_code in [200, 204]
            print(f"   Delete Test: {'✅ Success' if delete_success else '❌ Failed'} ({delete_response.status_code if delete_response else 'No response'})")
            self.test_results["CMS Delete"] = delete_success
            
            # If delete was successful, remove from cleanup tracking
            if delete_success:
                self.created_collections.discard(delete_test_collection)
        else:
            print("   Delete Test: ❌ Failed (Could not create test collection)")
            self.test_results["CMS Delete"] = False
        
        # Test 4: Load Balancer Health Detection
        print("\n🧪 Test 4: Load Balancer Health Detection")
        
        status_response = self.make_request('GET', f"{self.base_url}/status", timeout=15)
        if status_response and status_response.status_code == 200:
            status = status_response.json()
            healthy_instances = status.get('healthy_instances', 0)
            total_instances = status.get('total_instances', 2)
            
            # Should show 1/2 healthy (replica only)
            health_detection_success = healthy_instances == 1 and total_instances == 2
            print(f"   Health Detection: {'✅ Success' if health_detection_success else '❌ Failed'} ({healthy_instances}/{total_instances} healthy)")
            self.test_results["Health Detection"] = health_detection_success
        else:
            print("   Health Detection: ❌ Failed (Cannot check status)")
            self.test_results["Health Detection"] = False
        
        return self.test_results

    def cleanup_successful_tests(self):
        """Clean up test data ONLY from successful tests"""
        print("\n🧹 SELECTIVE CLEANUP: Cleaning up data from successful tests only")
        print("="*60)
        
        successful_tests = [name for name, success in self.test_results.items() if success]
        failed_tests = [name for name, success in self.test_results.items() if not success]
        
        print(f"✅ Successful tests: {len(successful_tests)} - Data will be cleaned")
        print(f"❌ Failed tests: {len(failed_tests)} - Data preserved for debugging")
        
        if not successful_tests:
            print("\n⚠️  No successful tests - No cleanup needed")
            return
        
        # Clean up collections from successful tests
        collections_to_clean = []
        
        # Only clean collections if their associated tests were successful
        for collection_name in self.created_collections:
            # Check if this collection was created during successful tests
            should_clean = False
            
            if "upload" in collection_name and self.test_results.get("CMS Upload", False):
                should_clean = True
            elif "delete" in collection_name and self.test_results.get("CMS Delete", False):
                should_clean = True
            # Add more logic for other test types as needed
            
            if should_clean:
                collections_to_clean.append(collection_name)
        
        if collections_to_clean:
            print(f"\n🗑️  Cleaning {len(collections_to_clean)} collections from successful tests:")
            
            for collection_name in collections_to_clean:
                print(f"   Deleting collection: {collection_name}")
                
                delete_response = self.make_request(
                    'DELETE',
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                    timeout=15
                )
                
                if delete_response and delete_response.status_code in [200, 204]:
                    print(f"   ✅ Cleaned: {collection_name}")
                else:
                    print(f"   ❌ Failed to clean: {collection_name}")
        
        # Report preserved data for debugging
        preserved_collections = self.created_collections - set(collections_to_clean)
        if preserved_collections:
            print(f"\n🔍 PRESERVED FOR DEBUGGING: {len(preserved_collections)} collections")
            for collection_name in preserved_collections:
                print(f"   📌 {collection_name} (from failed test)")
        
        print("\n✅ Selective cleanup complete")

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n📊 USE CASE 2 TEST RESULTS SUMMARY:")
        print("="*50)
        
        passed_tests = sum(1 for success in self.test_results.values() if success)
        total_tests = len(self.test_results)
        
        for test_name, success in self.test_results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"   {test_name}: {status}")
        
        print(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
        
        if passed_tests == total_tests:
            print("\n🎉 USE CASE 2 SUCCESS: CMS operations work seamlessly during primary failure!")
        elif passed_tests > 0:
            print(f"\n⚠️  USE CASE 2 PARTIAL SUCCESS: {passed_tests}/{total_tests} operations succeeded during primary failure")
        else:
            print("\n❌ USE CASE 2 FAILED: No operations succeeded during primary failure")
        
        return passed_tests == total_tests

    def run(self):
        """Main execution with all safeguards"""
        print("🚨 USE CASE 2: PRIMARY INSTANCE DOWN - MANUAL TESTING")
        
        # Step 1: Check initial health
        print("\n📋 Step 1: Initial Health Check")
        initial_primary, initial_replica = self.check_system_health()
        
        if not initial_replica:
            print("\n❌ Cannot proceed: Replica instance is unhealthy")
            print("   Fix replica health before attempting USE CASE 2 testing")
            return False
        
        # Step 2: Require manual confirmation
        print("\n📋 Step 2: Manual Confirmation Required")
        if not self.require_manual_confirmation():
            return False
        
        # Step 3: Verify primary is actually down (CRITICAL SAFEGUARD)
        print("\n📋 Step 3: Safety Verification")
        if not self.verify_primary_is_down():
            return False
        
        # Step 4: Run actual testing
        print("\n📋 Step 4: Failover Testing")
        test_results = self.run_use_case_2_testing()
        
        # Step 5: Print summary
        print("\n📋 Step 5: Test Summary")
        overall_success = self.print_test_summary()
        
        # Step 6: Selective cleanup
        print("\n📋 Step 6: Selective Cleanup")
        self.cleanup_successful_tests()
        
        # Step 7: Next steps guidance
        print("\n📋 NEXT STEPS:")
        print("1. 🔄 Restore primary instance via Render dashboard (Resume/Restart)")
        print("2. ⏳ Wait 1-2 minutes for WAL sync to complete")
        print("3. 🔍 Verify documents uploaded during failure appear on primary")
        print("4. ✅ Confirm zero data loss and complete sync")
        
        return overall_success

def main():
    """Main entry point with additional safeguards"""
    
    print("="*80)
    print("🚨 USE CASE 2: PRIMARY INSTANCE DOWN - MANUAL TESTING PROTOCOL")
    print("="*80)
    
    # Command line argument safeguard
    if len(sys.argv) < 2 or sys.argv[1] != "--manual-confirmed":
        print("\n🛑 SAFEGUARD: This test requires explicit confirmation")
        print("\n📋 To run USE CASE 2 testing, use:")
        print("   python use_case_2_manual_testing.py --manual-confirmed")
        print("\n⚠️  REMEMBER: You must suspend the primary instance FIRST")
        print("   1. Go to Render dashboard → chroma-primary → Suspend")
        print("   2. Wait 30-60 seconds")
        print("   3. Then run this script with --manual-confirmed")
        sys.exit(1)
    
    tester = UseCase2ManualTester()
    success = tester.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 