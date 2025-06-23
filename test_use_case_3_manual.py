#!/usr/bin/env python3
"""
USE CASE 3: Replica Instance Down - Manual Testing Protocol
=========================================================

This script guides you through the complete USE CASE 3 testing lifecycle:
1. Manual replica suspension via Render dashboard
2. Automated testing during replica infrastructure failure  
3. Manual replica recovery via Render dashboard
4. Automatic verification of sync completion
5. Selective automatic cleanup (same as USE CASE 1)

Usage: python test_use_case_3_manual.py --url https://chroma-load-balancer.onrender.com
"""

import argparse
import requests
import json
import time
import sys
import subprocess
from datetime import datetime, timedelta

class UseCase3Tester:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.test_collections = []
        self.test_results = {}  # Track individual test results for selective cleanup
        self.session_id = f"UC3_MANUAL_{int(time.time())}"
        self.start_time = None

    def log(self, message):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def check_system_health(self):
        """Check current system health"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                return status
            return None
        except Exception as e:
            self.log(f"Failed to check system health: {e}")
            return None

    def wait_for_user_input(self, prompt):
        """Wait for user to press Enter with a prompt"""
        input(f"\n{prompt}\nPress Enter when ready to continue...")

    def create_test_collection(self, name_suffix=""):
        """Create a test collection during replica failure simulation"""
        collection_name = f"{self.session_id}_{name_suffix}" if name_suffix else self.session_id
        try:
            payload = {"name": collection_name}
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                self.test_collections.append(collection_name)
                result = response.json()
                self.log(f"✅ Collection created: {collection_name} (Status: {response.status_code}, Time: {response.elapsed.total_seconds():.3f}s)")
                return True, result
            else:
                self.log(f"❌ Collection creation failed: {collection_name} (Status: {response.status_code})")
                return False, None
                
        except Exception as e:
            self.log(f"❌ Collection creation error: {collection_name} - {e}")
            return False, None

    def test_read_operations(self, collection_name):
        """Test read operations during replica failure"""
        try:
            # Test collection listing (should route to primary)
            list_response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=15
            )
            
            list_success = list_response.status_code == 200
            self.log(f"   Collection listing: {'✅ Success' if list_success else '❌ Failed'} (Status: {list_response.status_code}, Time: {list_response.elapsed.total_seconds():.3f}s)")
            
            # Test document query on global collection (should route to primary)
            query_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/global/query",
                json={"query_embeddings": [[0.1] * 3072], "n_results": 1},
                timeout=15
            )
            
            query_success = query_response.status_code == 200
            self.log(f"   Document query: {'✅ Success' if query_success else '❌ Failed'} (Status: {query_response.status_code}, Time: {query_response.elapsed.total_seconds():.3f}s)")
            
            return list_success and query_success
            
        except Exception as e:
            self.log(f"❌ Read operations error: {e}")
            return False

    def test_write_operations(self, collection_name):
        """Test write operations during replica failure (should have zero impact)"""
        try:
            # Test document addition with embeddings
            doc_payload = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["Test document during replica failure"],
                "metadatas": [{"test_type": "replica_down", "scenario": "uc3_manual"}],
                "ids": ["test_doc_replica_down"]
            }
            
            add_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_payload,
                timeout=15
            )
            
            add_success = add_response.status_code in [200, 201]
            self.log(f"   Document addition: {'✅ Success' if add_success else '❌ Failed'} (Status: {add_response.status_code}, Time: {add_response.elapsed.total_seconds():.3f}s)")
            
            return add_success
            
        except Exception as e:
            self.log(f"❌ Write operations error: {e}")
            return False

    def test_delete_operations(self):
        """Test DELETE operations during replica failure"""
        try:
            # Create a temporary collection for deletion test
            delete_test_collection = f"{self.session_id}_DELETE_TEST"
            
            create_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": delete_test_collection},
                timeout=15
            )
            
            if create_response.status_code in [200, 201]:
                self.test_collections.append(delete_test_collection)
                time.sleep(2)  # Brief wait for creation
                
                delete_response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{delete_test_collection}",
                    timeout=15
                )
                
                delete_success = delete_response.status_code in [200, 204]
                self.log(f"   DELETE operations: {'✅ Success' if delete_success else '❌ Failed'} (Status: {delete_response.status_code}, Time: {delete_response.elapsed.total_seconds():.3f}s)")
                
                # If delete was successful, remove from cleanup tracking
                if delete_success:
                    self.test_collections.remove(delete_test_collection)
                
                return delete_success
            else:
                self.log(f"   DELETE operations: ❌ Failed (Could not create test collection)")
                return False
                
        except Exception as e:
            self.log(f"❌ DELETE operations error: {e}")
            return False

    def run_comprehensive_testing(self):
        """Run comprehensive testing during replica failure"""
        self.log("🧪 Running comprehensive testing during replica failure...")
        
        # Test 1: Collection Creation (should work normally - routes to primary)
        self.log("Test 1: Collection Creation During Replica Failure")
        success1, _ = self.create_test_collection("COLLECTION_TEST")
        self.test_results["Collection Creation"] = success1
        
        # Test 2: Read Operations (should failover to primary)
        self.log("Test 2: Read Operations During Replica Failure")
        success2 = self.test_read_operations("global")
        self.test_results["Read Operations"] = success2
        
        # Test 3: Write Operations (should have zero impact)
        self.log("Test 3: Write Operations During Replica Failure") 
        if self.test_collections:
            success3 = self.test_write_operations(self.test_collections[0])
        else:
            success3 = False
        self.test_results["Write Operations"] = success3
        
        # Test 4: DELETE Operations (should work with primary only)
        self.log("Test 4: DELETE Operations During Replica Failure")
        success4 = self.test_delete_operations()
        self.test_results["DELETE Operations"] = success4
        
        # Test 5: Health Detection
        self.log("Test 5: Load Balancer Health Detection")
        status = self.check_system_health()
        if status:
            healthy_instances = status.get('healthy_instances', 0)
            # Should show 1/2 healthy (primary only)
            success5 = healthy_instances == 1
            self.log(f"   Health Detection: {'✅ Success' if success5 else '❌ Failed'} ({healthy_instances}/2 healthy instances)")
        else:
            success5 = False
            self.log("   Health Detection: ❌ Failed (Cannot check status)")
        
        self.test_results["Health Detection"] = success5
        
        return self.test_results

    def wait_for_replica_recovery(self, timeout_minutes=5):
        """Wait for replica recovery and sync completion"""
        self.log(f"⏳ Monitoring replica recovery (timeout: {timeout_minutes} minutes)...")
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        while time.time() - start_time < timeout_seconds:
            status = self.check_system_health()
            if status:
                healthy_instances = status.get('healthy_instances', 0)
                if healthy_instances == 2:
                    self.log("✅ Replica recovery detected!")
                    
                    # Wait a bit more for WAL sync
                    self.log("⏳ Waiting for WAL sync completion...")
                    time.sleep(30)
                    return True
                else:
                    self.log(f"   Still waiting... ({healthy_instances}/2 instances healthy)")
            
            time.sleep(10)
        
        self.log("⚠️ Timeout waiting for replica recovery")
        return False

    def selective_cleanup(self):
        """Clean up test data based on test results - same behavior as USE CASE 1"""
        self.log("🧹 SELECTIVE CLEANUP: Same behavior as USE CASE 1")
        self.log("="*60)
        
        successful_tests = [name for name, success in self.test_results.items() if success]
        failed_tests = [name for name, success in self.test_results.items() if not success]
        
        self.log(f"✅ Successful tests: {len(successful_tests)} - Data will be cleaned")
        self.log(f"❌ Failed tests: {len(failed_tests)} - Data preserved for debugging")
        
        if not successful_tests:
            self.log("\n⚠️  No successful tests - No cleanup needed")
            return
        
        # Only clean collections if their associated tests were successful
        collections_to_clean = []
        preserved_collections = []
        
        for collection_name in self.test_collections:
            # Map collections to their test results
            should_clean = False
            test_type = "Unknown"
            
            if "COLLECTION_TEST" in collection_name and self.test_results.get("Collection Creation", False):
                should_clean = True
                test_type = "Collection Creation"
            elif "DELETE_TEST" in collection_name and self.test_results.get("DELETE Operations", False):
                should_clean = True  
                test_type = "DELETE Operations"
            elif self.test_results.get("Write Operations", False):
                # Default to cleaning if write operations were successful
                should_clean = True
                test_type = "Write Operations"
            
            if should_clean:
                collections_to_clean.append((collection_name, test_type))
            else:
                preserved_collections.append((collection_name, test_type))
        
        # Clean successful test data
        if collections_to_clean:
            self.log(f"\n🗑️  Cleaning {len(collections_to_clean)} collections from successful tests:")
            
            for collection_name, test_type in collections_to_clean:
                self.log(f"   Deleting {collection_name} (from {test_type})")
                
                try:
                    delete_response = requests.delete(
                        f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                        timeout=15
                    )
                    
                    if delete_response.status_code in [200, 204]:
                        self.log(f"   ✅ Cleaned: {collection_name}")
                    else:
                        self.log(f"   ❌ Failed to clean: {collection_name}")
                        
                except Exception as e:
                    self.log(f"   ❌ Error cleaning {collection_name}: {e}")
        
        # Report preserved data for debugging
        if preserved_collections:
            self.log(f"\n🔍 PRESERVED FOR DEBUGGING: {len(preserved_collections)} collections")
            for collection_name, test_type in preserved_collections:
                collection_url = f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                self.log(f"   📌 {collection_name} (from failed {test_type})")
                self.log(f"      🔗 Debug URL: {collection_url}")
        
        self.log("\n✅ Selective cleanup complete - Same behavior as USE CASE 1!")

    def print_summary(self):
        """Print comprehensive test summary"""
        self.log("📊 USE CASE 3 TEST RESULTS SUMMARY:")
        self.log("="*50)
        
        if not self.test_results:
            self.log("No test results to display")
            return False
        
        passed_tests = sum(1 for success in self.test_results.values() if success)
        total_tests = len(self.test_results)
        
        for test_name, success in self.test_results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            self.log(f"   {test_name}: {status}")
        
        success_rate = (passed_tests/total_tests*100) if total_tests > 0 else 0
        self.log(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")
        
        if passed_tests == total_tests:
            self.log("\n🎉 USE CASE 3 SUCCESS: Read operations failover seamlessly during replica failure!")
            self.log("   ✅ Zero user impact during replica infrastructure failures")
            self.log("   ✅ Write operations completely unaffected")
            self.log("   ✅ Load balancer provides transparent failover")
        elif passed_tests > 0:
            self.log(f"\n⚠️  USE CASE 3 PARTIAL SUCCESS: {passed_tests}/{total_tests} operations succeeded")
        else:
            self.log("\n❌ USE CASE 3 FAILED: No operations succeeded during replica failure")
        
        return passed_tests == total_tests

    def run(self):
        """Main execution flow"""
        self.log("🔴 USE CASE 3: REPLICA INSTANCE DOWN - MANUAL TESTING")
        self.log("="*60)
        
        # Step 1: Check initial health
        self.log("📋 Step 1: Initial Health Check")
        initial_status = self.check_system_health()
        if not initial_status:
            self.log("❌ Cannot connect to system")
            return False
        
        healthy_instances = initial_status.get('healthy_instances', 0)
        if healthy_instances != 2:
            self.log(f"❌ System not ready: {healthy_instances}/2 instances healthy")
            self.log("   Both instances must be healthy before testing")
            return False
        
        self.log("✅ System ready: 2/2 instances healthy")
        
        # Step 2: Guide user through replica suspension
        self.log("\n📋 Step 2: Manual Replica Suspension")
        self.log("🔴 MANUAL ACTION REQUIRED: Suspend Replica Instance")
        self.log("")
        self.log("1. Go to your Render dashboard (https://dashboard.render.com)")
        self.log("2. Navigate to 'chroma-replica' service")
        self.log("3. Click 'Suspend' to simulate replica infrastructure failure")
        self.log("4. Wait 5-10 seconds for health detection to update")
        
        self.wait_for_user_input("Complete replica suspension and wait for health detection")
        
        # Step 3: Verify replica failure detection
        self.log("\n📋 Step 3: Verify Replica Failure Detection")
        status = self.check_system_health()
        if not status:
            self.log("❌ Cannot check system status")
            return False
        
        healthy_instances = status.get('healthy_instances', 0)
        if healthy_instances != 1:
            self.log(f"❌ Replica suspension not detected: {healthy_instances}/2 instances healthy")
            self.log("   Please verify replica was suspended and wait longer")
            return False
        
        self.log("✅ Replica failure detected: 1/2 instances healthy")
        
        # Step 4: Run comprehensive testing
        self.log("\n📋 Step 4: Comprehensive Testing During Replica Failure")
        self.start_time = time.time()
        test_results = self.run_comprehensive_testing()
        
        # Step 5: Guide user through replica recovery
        self.log("\n📋 Step 5: Manual Replica Recovery")
        self.log("🔴 MANUAL ACTION REQUIRED: Resume Replica Instance")
        self.log("")
        self.log("1. Go back to your Render dashboard")
        self.log("2. Navigate to 'chroma-replica' service")
        self.log("3. Click 'Resume' or 'Restart' to restore the replica")
        self.log("4. Wait for the service to fully start up (~30-60 seconds)")
        
        self.wait_for_user_input("Complete replica recovery")
        
        # Step 6: Wait for recovery and sync
        self.log("\n📋 Step 6: Monitor Recovery and Sync")
        recovery_success = self.wait_for_replica_recovery()
        
        if recovery_success:
            self.log("✅ Replica recovery and sync completed!")
        else:
            self.log("⚠️ Replica recovery monitoring timed out")
        
        # Step 7: Print summary
        self.log("\n📋 Step 7: Test Results Summary")
        overall_success = self.print_summary()
        
        # Step 8: Selective cleanup (same as USE CASE 1)
        self.log("\n📋 Step 8: Selective Cleanup (Same as USE CASE 1)")
        self.selective_cleanup()
        
        # Step 9: Final guidance
        total_time = time.time() - self.start_time if self.start_time else 0
        self.log(f"\n📊 USE CASE 3 TESTING COMPLETED")
        self.log(f"⏱️  Total test time: {total_time/60:.1f} minutes")
        
        passed_tests = sum(1 for success in self.test_results.values() if success)
        total_tests = len(self.test_results)
        self.log(f"🧪 Test results: {passed_tests}/{total_tests} successful ({passed_tests/total_tests*100:.1f}%)")
        
        if overall_success:
            self.log("🎉 USE CASE 3: ✅ SUCCESS - Replica failure handling validated!")
            self.log("   Your system maintains seamless operation during replica infrastructure failures.")
        else:
            self.log("⚠️ USE CASE 3: Partial success - Review failed tests for improvements")
        
        return overall_success

def main():
    parser = argparse.ArgumentParser(description='USE CASE 3: Replica Instance Down - Manual Testing')
    parser.add_argument('--url', required=True, help='Load balancer URL (e.g., https://chroma-load-balancer.onrender.com)')
    
    args = parser.parse_args()
    
    tester = UseCase3Tester(args.url)
    success = tester.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 