#!/usr/bin/env python3
"""
DELETE Sync Unified Fix Validation Test
Tests the unified DELETE sync fix for both-target operations
"""

import requests
import time
import uuid
import json
from datetime import datetime
from logging_config import setup_test_logging

class DeleteSyncUnifiedFixTest:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.test_session = f"DELETE_UNIFIED_FIX_{int(time.time())}"
        self.logger = setup_test_logging("delete_sync_unified_fix")
        self.test_collections = []
        
    def log(self, message):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        self.logger.info(message)
        
    def wait_for_system_ready(self, timeout=30):
        """Wait for system to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/status", timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    if status.get('healthy_instances', 0) >= 2:
                        self.log(f"✅ System ready: {status['healthy_instances']}/2 instances healthy")
                        return True
                    else:
                        self.log(f"⏳ Waiting for system: {status.get('healthy_instances', 0)}/2 instances healthy")
                        time.sleep(5)
                else:
                    self.log(f"⏳ System not ready: HTTP {response.status_code}")
                    time.sleep(5)
            except Exception as e:
                self.log(f"⏳ Waiting for system: {e}")
                time.sleep(5)
        
        self.log(f"❌ System not ready after {timeout}s")
        return False
    
    def create_test_collection(self, collection_name):
        """Create a test collection"""
        self.log(f"🔧 Creating test collection: {collection_name}")
        
        try:
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={
                    "name": collection_name,
                    "metadata": {"test": "delete_sync_unified_fix"}
                },
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                self.log(f"✅ Collection created: {collection_name}")
                self.test_collections.append(collection_name)
                return True
            else:
                self.log(f"❌ Collection creation failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Collection creation error: {e}")
            return False
    
    def delete_test_collection(self, collection_name):
        """Delete a test collection"""
        self.log(f"🗑️ Deleting test collection: {collection_name}")
        
        try:
            response = requests.delete(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                timeout=30
            )
            
            if response.status_code in [200, 204]:
                self.log(f"✅ Collection deleted: {collection_name} (HTTP {response.status_code})")
                return True
            else:
                self.log(f"❌ Collection deletion failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Collection deletion error: {e}")
            return False
    
    def verify_collection_deleted_from_both_instances(self, collection_name):
        """Verify collection is deleted from both instances"""
        self.log(f"🔍 Verifying collection '{collection_name}' is deleted from both instances")
        
        instances = [
            ("primary", "https://chroma-primary.onrender.com"),
            ("replica", "https://chroma-replica.onrender.com")
        ]
        
        verification_results = {}
        
        for instance_name, instance_url in instances:
            try:
                response = requests.get(
                    f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                    timeout=10
                )
                
                if response.status_code == 200:
                    collections = response.json()
                    collection_exists = any(c.get('name') == collection_name for c in collections)
                    
                    if collection_exists:
                        found_collection = next((c for c in collections if c.get('name') == collection_name), None)
                        collection_id = found_collection.get('id', 'unknown')[:8] if found_collection else 'unknown'
                        self.log(f"❌ VERIFICATION FAILED: Collection '{collection_name}' still exists on {instance_name} (ID: {collection_id})")
                        verification_results[instance_name] = False
                    else:
                        self.log(f"✅ VERIFICATION PASSED: Collection '{collection_name}' deleted from {instance_name}")
                        verification_results[instance_name] = True
                else:
                    self.log(f"⚠️ Cannot verify {instance_name}: HTTP {response.status_code}")
                    verification_results[instance_name] = None
                    
            except Exception as e:
                self.log(f"❌ Verification error for {instance_name}: {e}")
                verification_results[instance_name] = None
        
        return verification_results
    
    def wait_for_wal_sync_completion(self, timeout=60):
        """Wait for WAL sync to complete"""
        self.log(f"⏳ Waiting for WAL sync completion (timeout: {timeout}s)")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/wal/status", timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    pending_writes = status.get('wal_system', {}).get('pending_writes', 0)
                    
                    if pending_writes == 0:
                        self.log(f"✅ WAL sync completed: 0 pending writes")
                        return True
                    else:
                        self.log(f"⏳ WAL sync in progress: {pending_writes} pending writes")
                        time.sleep(5)
                else:
                    self.log(f"⚠️ Cannot check WAL status: HTTP {response.status_code}")
                    time.sleep(5)
            except Exception as e:
                self.log(f"⚠️ WAL status check error: {e}")
                time.sleep(5)
        
        self.log(f"⚠️ WAL sync timeout after {timeout}s")
        return False
    
    def run_test(self):
        """Run the comprehensive DELETE sync test"""
        self.log("🎯 STARTING DELETE SYNC UNIFIED FIX VALIDATION TEST")
        self.log("=" * 60)
        
        # Step 1: Wait for system to be ready
        if not self.wait_for_system_ready():
            self.log("❌ TEST FAILED: System not ready")
            return False
        
        # Step 2: Create test collection
        collection_name = f"{self.test_session}_DELETE_TEST"
        if not self.create_test_collection(collection_name):
            self.log("❌ TEST FAILED: Could not create test collection")
            return False
        
        # Step 3: Wait for creation to sync
        self.log("⏳ Waiting for collection creation to sync...")
        time.sleep(10)
        
        # Step 4: Delete test collection
        if not self.delete_test_collection(collection_name):
            self.log("❌ TEST FAILED: Could not delete test collection")
            return False
        
        # Step 5: Wait for WAL sync to complete
        if not self.wait_for_wal_sync_completion():
            self.log("⚠️ WAL sync may still be in progress")
        
        # Step 6: Wait additional time for sync completion
        self.log("⏳ Waiting for DELETE sync to complete...")
        time.sleep(30)
        
        # Step 7: Verify collection is deleted from both instances
        verification_results = self.verify_collection_deleted_from_both_instances(collection_name)
        
        # Step 8: Analyze results
        primary_deleted = verification_results.get('primary', False)
        replica_deleted = verification_results.get('replica', False)
        
        if primary_deleted and replica_deleted:
            self.log("🎉 DELETE SYNC UNIFIED FIX VALIDATION: PASSED!")
            self.log("    ✅ Collection properly deleted from PRIMARY")
            self.log("    ✅ Collection properly deleted from REPLICA")
            self.log("    ✅ DELETE sync fix is working correctly!")
            return True
        else:
            self.log("❌ DELETE SYNC UNIFIED FIX VALIDATION: FAILED!")
            self.log(f"    PRIMARY deleted: {primary_deleted}")
            self.log(f"    REPLICA deleted: {replica_deleted}")
            self.log("    ❌ DELETE sync fix still has issues")
            return False

def main():
    test = DeleteSyncUnifiedFixTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 DELETE SYNC UNIFIED FIX: VALIDATION PASSED!")
        print("The critical DELETE sync issue has been resolved.")
    else:
        print("\n❌ DELETE SYNC UNIFIED FIX: VALIDATION FAILED!")
        print("The DELETE sync issue still needs more work.")
    
    return success

if __name__ == "__main__":
    main() 