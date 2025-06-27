#!/usr/bin/env python3

"""
USE CASE 2: Primary Instance Down - FIXED VALIDATION
This version includes proper validation that detects WAL sync failures
"""

import requests
import time
import argparse
import sys
from enhanced_verification_base import EnhancedVerificationBase

class UseCase2FixedTester(EnhancedVerificationBase):
    def __init__(self, base_url):
        super().__init__(base_url)
        self.base_url = base_url
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
        self.test_collections = []
        self.test_results = {}
        self.documents_added_during_failure = {}
        self.start_time = None
        
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def check_system_health(self):
        """Check system health via load balancer"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
        return None
        
    def create_test_collection(self, name_suffix="", test_name=None):
        """Create a test collection during failure"""
        import random
        timestamp = int(time.time())
        random_id = f"{random.randint(1000, 9999)}"
        collection_name = f"UC2_FIXED_{timestamp}_{name_suffix}_{random_id}"
        
        try:
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json={"name": collection_name},
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                self.test_collections.append(collection_name)
                if test_name and test_name not in self.test_results:
                    self.test_results[test_name] = {'success': True, 'collections': []}
                if test_name:
                    self.test_results[test_name]['collections'].append(collection_name)
                    
                return collection_name, response.status_code, response.elapsed.total_seconds()
            else:
                return None, response.status_code, response.elapsed.total_seconds()
                
        except Exception as e:
            self.log(f"Collection creation error: {e}", "ERROR")
            return None, 0, 0
            
    def verify_primary_sync(self):
        """CRITICAL: Verify collections created during failure actually exist on PRIMARY instance"""
        self.log("🔍 CRITICAL VALIDATION: Checking PRIMARY instance for collections created during failure...")
        
        if not self.test_collections:
            self.log("   ℹ️ No test collections to verify")
            return True
            
        try:
            # Check PRIMARY instance directly (not via load balancer)
            primary_response = requests.get(
                f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=10
            )
            
            if primary_response.status_code != 200:
                self.log(f"   ❌ Cannot access primary instance: HTTP {primary_response.status_code}")
                return False
                
            primary_collections = primary_response.json()
            primary_collection_names = [c['name'] for c in primary_collections]
            
            # Check how many of our test collections exist on primary
            synced_to_primary = [name for name in self.test_collections if name in primary_collection_names]
            missing_from_primary = [name for name in self.test_collections if name not in primary_collection_names]
            
            self.log(f"   📊 PRIMARY SYNC VALIDATION:")
            self.log(f"      Collections created during primary failure: {len(self.test_collections)}")
            self.log(f"      Collections found on primary after recovery: {len(synced_to_primary)}")
            self.log(f"      Sync success rate: {len(synced_to_primary)}/{len(self.test_collections)} = {len(synced_to_primary)/len(self.test_collections)*100:.1f}%")
            
            if len(synced_to_primary) == len(self.test_collections):
                self.log(f"   ✅ PERFECT: All collections synced from replica to primary!")
                return True
            else:
                self.log(f"   ❌ SYNC FAILURE: {len(missing_from_primary)} collections missing from primary")
                self.log(f"   📋 Missing collections:")
                for missing in missing_from_primary:
                    self.log(f"      - {missing}")
                self.log(f"   🚨 This proves WAL sync from replica→primary is BROKEN")
                return False
                
        except Exception as e:
            self.log(f"   ❌ Error checking primary instance: {e}")
            return False
            
    def verify_load_balancer_access(self):
        """Check if collections are accessible via load balancer"""
        self.log("🔍 Checking load balancer access to collections...")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=10
            )
            
            if response.status_code != 200:
                self.log(f"   ❌ Cannot access load balancer: HTTP {response.status_code}")
                return False
                
            collections = response.json()
            collection_names = [c['name'] for c in collections]
            found_via_lb = [name for name in self.test_collections if name in collection_names]
            
            self.log(f"   📊 LOAD BALANCER ACCESS:")
            self.log(f"      Collections accessible via load balancer: {len(found_via_lb)}/{len(self.test_collections)}")
            
            return len(found_via_lb) == len(self.test_collections)
            
        except Exception as e:
            self.log(f"   ❌ Error checking load balancer: {e}")
            return False
            
    def test_operations_during_failure(self):
        """Test operations while primary is down"""
        self.log("🧪 Testing operations during primary failure...")
        
        success_count = 0
        total_tests = 2
        
        # Test 1: Collection Creation
        self.log("Test 1: Collection Creation")
        collection_name, status_code, duration = self.create_test_collection("CREATE", "collection_creation")
        if collection_name:
            self.log(f"✅ Collection created: {collection_name} (Status: {status_code}, Time: {duration:.3f}s)")
            success_count += 1
        else:
            self.log(f"❌ Collection creation failed (Status: {status_code}, Time: {duration:.3f}s)")
            if "collection_creation" not in self.test_results:
                self.test_results["collection_creation"] = {'success': False, 'collections': []}
            
        # Test 2: Additional Collection
        self.log("Test 2: Additional Collection Creation")
        collection_name2, status_code2, duration2 = self.create_test_collection("ADDITIONAL", "additional_collection")
        if collection_name2:
            self.log(f"✅ Collection created: {collection_name2} (Status: {status_code2}, Time: {duration2:.3f}s)")
            success_count += 1
        else:
            self.log(f"❌ Collection creation failed (Status: {status_code2}, Time: {duration2:.3f}s)")
            if "additional_collection" not in self.test_results:
                self.test_results["additional_collection"] = {'success': False, 'collections': []}
        
        self.log(f"📊 Operations during failure: {success_count}/{total_tests} successful ({success_count/total_tests*100:.1f}%)")
        return success_count, total_tests
        
    def wait_for_user(self, message):
        """Wait for user to perform manual action"""
        print("\n🔴 " + message.strip())
        input("Press Enter when ready to continue...")
        
    def run_test(self):
        """Run the fixed validation test"""
        print("="*80)
        print("🚀 USE CASE 2: FIXED VALIDATION TEST")
        print("="*80)
        
        # Step 1: Initial Health Check
        self.log("📋 Step 1: Initial System Health Check")
        initial_status = self.check_system_health()
        if not initial_status:
            self.log("❌ Cannot connect to system", "ERROR")
            return False
            
        healthy_instances = initial_status.get('healthy_instances', 0)
        self.log(f"✅ Initial status: {healthy_instances}/2 instances healthy")
        
        # Step 2: Manual Primary Suspension
        self.wait_for_user("""
MANUAL ACTION REQUIRED: Suspend Primary Instance
        
1. Go to your Render dashboard (https://dashboard.render.com)
2. Navigate to 'chroma-primary' service
3. Click 'Suspend' to simulate infrastructure failure
4. Wait 5-10 seconds for health detection to update
        """)
        
        # Step 3: Verify Primary Down
        self.log("📋 Step 3: Verifying primary failure detection...")
        time.sleep(10)
        
        # Step 4: Test Operations During Failure
        self.log("📋 Step 4: Testing operations during infrastructure failure...")
        success_count, total_tests = self.test_operations_during_failure()
        
        if success_count == 0:
            self.log("❌ All operations failed during primary outage", "ERROR")
            return False
            
        # Step 5: Manual Primary Recovery
        self.wait_for_user("""
MANUAL ACTION REQUIRED: Resume Primary Instance
        
1. Go back to your Render dashboard
2. Navigate to 'chroma-primary' service  
3. Click 'Resume' or 'Restart' to restore the primary
4. Wait for the service to fully start up (~30-60 seconds)
        """)
        
        # Step 6: Wait for Recovery
        self.log("📋 Step 6: Waiting for system recovery...")
        time.sleep(60)  # Wait for recovery and sync
        
        # Step 7: CRITICAL - Test Primary Sync (This will detect the real issue)
        self.log("📋 Step 7: CRITICAL VALIDATION - Testing replica→primary sync...")
        
        # Check load balancer access first
        lb_access_ok = self.verify_load_balancer_access()
        
        # CRITICAL: Check primary instance sync 
        primary_sync_ok = self.verify_primary_sync()
        
        # Determine test result
        if success_count >= total_tests * 0.8 and lb_access_ok and primary_sync_ok:
            self.log("🎉 TEST RESULT: ✅ SUCCESS - All validation passed!")
            self.log("   - Operations continued during failure ✅")
            self.log("   - Load balancer access working ✅") 
            self.log("   - Primary sync working ✅")
            return True
        else:
            self.log("🚨 TEST RESULT: ❌ FAILURE - Critical issues detected!")
            if success_count < total_tests * 0.8:
                self.log(f"   - Operations during failure: FAILED ({success_count}/{total_tests})")
            if not lb_access_ok:
                self.log("   - Load balancer access: FAILED")
            if not primary_sync_ok:
                self.log("   - Primary sync: FAILED (CORE ISSUE)")
                self.log("   - WAL sync system is broken")
            return False

def main():
    parser = argparse.ArgumentParser(description='USE CASE 2: Fixed Validation Test')
    parser.add_argument('--url', required=True, help='Load balancer URL')
    args = parser.parse_args()
    
    tester = UseCase2FixedTester(args.url)
    success = tester.run_test()
    
    if success:
        print("\n✅ Fixed validation test PASSED - System working correctly")
    else:
        print("\n❌ Fixed validation test FAILED - Issues detected that original test missed")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 