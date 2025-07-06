#!/usr/bin/env python3
"""
DELETE Sync Validation Test
Focused test to validate the DELETE sync fix works correctly
"""

import requests
import time
import uuid
import json
from datetime import datetime
from logging_config import setup_test_logging

class DeleteSyncValidator:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.test_session = f"DELETE_VALIDATION_{int(time.time())}"
        self.logger = setup_test_logging("delete_sync_validation")
        self.test_collections = []
        
    def log(self, message):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        self.logger.info(message)
    
    def check_system_health(self):
        """Verify system is healthy before testing"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                healthy = status.get('healthy_instances', 0)
                total = status.get('total_instances', 0)
                
                if healthy == total and total == 2:
                    self.log(f"✅ System healthy: {healthy}/{total} instances ready")
                    return True
                else:
                    self.log(f"❌ System not ready: {healthy}/{total} instances healthy")
                    return False
            else:
                self.log(f"❌ Status check failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ Health check error: {e}")
            return False
    
    def create_test_collection(self):
        """Create a test collection for deletion testing"""
        collection_name = f"{self.test_session}_DELETE_TEST_{uuid.uuid4().hex[:8]}"
        
        try:
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name},
                timeout=15
            )
            
            if response.status_code in [200, 201]:
                self.test_collections.append(collection_name)
                self.log(f"✅ Test collection created: {collection_name}")
                return collection_name
            else:
                self.log(f"❌ Collection creation failed: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            self.log(f"❌ Collection creation error: {e}")
            return None
    
    def delete_collection_via_load_balancer(self, collection_name):
        """Delete collection through load balancer"""
        try:
            response = requests.delete(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                timeout=15
            )
            
            self.log(f"🗑️ DELETE request: HTTP {response.status_code} in {response.elapsed.total_seconds():.3f}s")
            return response.status_code in [200, 204]
            
        except Exception as e:
            self.log(f"❌ DELETE error: {e}")
            return False
    
    def verify_collection_deleted_on_instance(self, instance_url, collection_name):
        """Verify collection is deleted from specific instance"""
        try:
            response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=10
            )
            
            if response.status_code == 200:
                collections = response.json()
                collection_exists = any(c.get('name') == collection_name for c in collections)
                return not collection_exists  # Return True if deleted (not exists)
            else:
                self.log(f"❌ Cannot verify {instance_url}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Verification error for {instance_url}: {e}")
            return False
    
    def wait_for_sync_completion(self, max_wait=90):
        """Wait for WAL sync to complete"""
        self.log(f"⏳ Waiting for WAL sync completion (max {max_wait}s)...")
        
        for elapsed in range(0, max_wait, 10):
            try:
                response = requests.get(f"{self.base_url}/wal/status", timeout=10)
                if response.status_code == 200:
                    wal_status = response.json()
                    pending = wal_status.get('wal_system', {}).get('pending_writes', -1)
                    
                    if pending == 0:
                        self.log(f"✅ WAL sync completed in {elapsed}s (0 pending writes)")
                        return True
                    else:
                        self.log(f"   WAL sync in progress: {pending} pending writes ({elapsed}s elapsed)")
                        
                time.sleep(10)
            except Exception as e:
                self.log(f"   WAL status check error: {e}")
                time.sleep(10)
        
        self.log(f"⏰ WAL sync timeout after {max_wait}s")
        return False
    
    def check_wal_debug_info(self):
        """Check WAL debug information for DELETE operations"""
        try:
            response = requests.get(f"{self.base_url}/admin/wal_debug", timeout=10)
            if response.status_code == 200:
                debug_info = response.json()
                delete_ops = debug_info.get('delete_operations', [])
                
                self.log(f"🔍 WAL Debug: Found {len(delete_ops)} recent DELETE operations")
                
                # Look for our test session operations
                session_deletes = [op for op in delete_ops if self.test_session in op.get('collection_id', '')]
                if session_deletes:
                    for op in session_deletes:
                        self.log(f"   DELETE {op['write_id']}: {op['collection_id']} - Status: {op['status']}")
                        self.log(f"   Target: {op['target_instance']}, Synced: {op['synced_instances']}")
                
                return True
            else:
                self.log(f"❌ WAL debug failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ WAL debug error: {e}")
            return False
    
    def run_validation_test(self):
        """Run comprehensive DELETE sync validation"""
        self.log("🧪 DELETE SYNC VALIDATION STARTING")
        self.log("=" * 50)
        
        # Step 1: Health check
        self.log("📋 Step 1: System Health Check")
        if not self.check_system_health():
            self.log("❌ VALIDATION FAILED: System not healthy")
            return False
        
        # Step 2: Create test collection
        self.log("\n📋 Step 2: Create Test Collection")
        collection_name = self.create_test_collection()
        if not collection_name:
            self.log("❌ VALIDATION FAILED: Could not create test collection")
            return False
        
        # Step 3: Wait for creation to propagate
        self.log("\n📋 Step 3: Wait for Creation Sync")
        time.sleep(5)
        
        # Step 4: Delete collection
        self.log("\n📋 Step 4: Delete Collection via Load Balancer")
        delete_success = self.delete_collection_via_load_balancer(collection_name)
        if not delete_success:
            self.log("❌ VALIDATION FAILED: DELETE operation failed")
            return False
        
        # Step 5: Wait for sync
        self.log("\n📋 Step 5: Wait for DELETE Sync")
        sync_completed = self.wait_for_sync_completion()
        if not sync_completed:
            self.log("⚠️ WARNING: WAL sync timeout - continuing with verification")
        
        # Step 6: Verify deletion on both instances
        self.log("\n📋 Step 6: Verify DELETE Sync on Both Instances")
        
        primary_deleted = self.verify_collection_deleted_on_instance(
            "https://chroma-primary.onrender.com", 
            collection_name
        )
        
        replica_deleted = self.verify_collection_deleted_on_instance(
            "https://chroma-replica.onrender.com", 
            collection_name
        )
        
        self.log(f"   Primary deleted: {'✅ YES' if primary_deleted else '❌ NO'}")
        self.log(f"   Replica deleted: {'✅ YES' if replica_deleted else '❌ NO'}")
        
        # Step 7: Check WAL debug info
        self.log("\n📋 Step 7: WAL Debug Information")
        self.check_wal_debug_info()
        
        # Step 8: Results
        self.log("\n📋 Step 8: Validation Results")
        
        if primary_deleted and replica_deleted:
            self.log("🎉 DELETE SYNC VALIDATION PASSED")
            self.log("   ✅ Collection successfully deleted from both instances")
            self.log("   ✅ DELETE sync working correctly")
            return True
        else:
            self.log("❌ DELETE SYNC VALIDATION FAILED")
            if not primary_deleted:
                self.log("   ❌ Collection still exists on PRIMARY")
            if not replica_deleted:
                self.log("   ❌ Collection still exists on REPLICA")
            self.log("   🔧 DELETE sync issue detected - fix may need additional work")
            return False
    
    def cleanup(self):
        """Clean up any remaining test collections"""
        if self.test_collections:
            self.log(f"\n🧹 Cleaning up {len(self.test_collections)} test collections...")
            for collection in self.test_collections:
                try:
                    requests.delete(
                        f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection}",
                        timeout=10
                    )
                except:
                    pass  # Cleanup is best effort

def main():
    validator = DeleteSyncValidator()
    
    try:
        success = validator.run_validation_test()
        
        print("\n" + "=" * 50)
        if success:
            print("🎉 DELETE SYNC FIX VALIDATION: PASSED")
            print("The DELETE sync issue has been successfully resolved!")
        else:
            print("❌ DELETE SYNC FIX VALIDATION: FAILED") 
            print("The DELETE sync issue may still exist - review logs for details")
        print("=" * 50)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n⏸️ Validation interrupted by user")
        return 2
    except Exception as e:
        print(f"\n💥 Validation error: {e}")
        return 3
    finally:
        validator.cleanup()

if __name__ == "__main__":
    exit(main()) 