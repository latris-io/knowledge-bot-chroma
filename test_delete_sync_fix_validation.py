#!/usr/bin/env python3
"""
DELETE Sync Fix Validation Test
Tests the critical bug fix for collection name vs UUID comparison in DELETE verification
"""

import requests
import time
import uuid
import json
from datetime import datetime
from logging_config import setup_test_logging

class DeleteSyncFixValidator:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.test_session = f"DELETE_FIX_VALIDATION_{int(time.time())}"
        self.logger = setup_test_logging("delete_sync_fix_validation")
        self.test_collections = []
        
    def log(self, message):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        self.logger.info(message)
        
    def check_system_health(self):
        """Check if both instances are healthy"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                healthy_instances = status.get('healthy_instances', 0)
                return healthy_instances >= 2, status
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
        return False, {}
        
    def create_test_collection(self, collection_name):
        """Create a test collection via load balancer"""
        try:
            payload = {
                "name": collection_name,
                "metadata": {"test_session": self.test_session}
            }
            
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json=payload,
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code in [200, 201]:
                self.test_collections.append(collection_name)
                self.log(f"✅ Collection created: {collection_name} (HTTP {response.status_code}, {duration:.3f}s)")
                return True
            else:
                self.log(f"❌ Collection creation failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Collection creation error: {e}")
            return False
            
    def delete_test_collection(self, collection_name):
        """Delete a test collection via load balancer"""
        try:
            start_time = time.time()
            response = requests.delete(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                timeout=30
            )
            duration = time.time() - start_time
            
            self.log(f"🗑️ DELETE request: HTTP {response.status_code} in {duration:.3f}s")
            
            if response.status_code == 200:
                return True, "success"
            elif response.status_code == 503:
                return False, "infrastructure_issue"
            else:
                return False, f"error_{response.status_code}"
                
        except Exception as e:
            self.log(f"❌ DELETE error: {e}")
            return False, "exception"
            
    def verify_collection_state(self, collection_name):
        """Verify collection state on both instances directly"""
        results = {}
        
        instances = [
            ("primary", "https://chroma-primary.onrender.com"),
            ("replica", "https://chroma-replica.onrender.com")
        ]
        
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
                        collection_uuid = next((c.get('id') for c in collections if c.get('name') == collection_name), 'unknown')
                        results[instance_name] = {
                            "exists": True,
                            "uuid": collection_uuid,
                            "total_collections": len(collections)
                        }
                        self.log(f"    📍 {instance_name}: Collection EXISTS (UUID: {collection_uuid[:8]}...)")
                    else:
                        results[instance_name] = {
                            "exists": False,
                            "uuid": None,
                            "total_collections": len(collections)
                        }
                        self.log(f"    📍 {instance_name}: Collection DELETED (total collections: {len(collections)})")
                else:
                    results[instance_name] = {"error": f"HTTP {response.status_code}"}
                    self.log(f"    📍 {instance_name}: API Error (HTTP {response.status_code})")
                    
            except Exception as e:
                results[instance_name] = {"error": str(e)}
                self.log(f"    📍 {instance_name}: Exception - {e}")
                
        return results
        
    def wait_for_sync(self, max_wait_seconds=60):
        """Wait for WAL sync to complete"""
        self.log(f"⏳ Waiting for WAL sync completion (max {max_wait_seconds}s)...")
        
        for i in range(max_wait_seconds):
            try:
                response = requests.get(f"{self.base_url}/wal/status", timeout=5)
                if response.status_code == 200:
                    wal_status = response.json()
                    pending_writes = wal_status.get('wal_system', {}).get('pending_writes', 0)
                    
                    if pending_writes == 0:
                        self.log(f"✅ WAL sync completed in {i}s (0 pending writes)")
                        return True
                        
            except Exception as e:
                self.log(f"⚠️ WAL status check failed: {e}")
                
            time.sleep(1)
            
        self.log(f"⏰ WAL sync timeout after {max_wait_seconds}s")
        return False
        
    def check_wal_debug_info(self, collection_name):
        """Check WAL debug information for the DELETE operation"""
        try:
            response = requests.get(f"{self.base_url}/admin/wal_debug", timeout=10)
            if response.status_code == 200:
                debug_info = response.json()
                
                # Look for DELETE operations involving our collection
                delete_ops = debug_info.get('delete_operations', [])
                relevant_deletes = [op for op in delete_ops if collection_name in op.get('path', '')]
                
                if relevant_deletes:
                    self.log(f"🔍 Found {len(relevant_deletes)} DELETE operations for '{collection_name}':")
                    for op in relevant_deletes:
                        self.log(f"    📋 Status: {op.get('status')}, Synced: {op.get('synced_instances')}")
                        self.log(f"    📋 Write ID: {op.get('write_id')}, Target: {op.get('target_instance')}")
                        
                return relevant_deletes
            else:
                self.log(f"❌ WAL debug failed: HTTP {response.status_code}")
                return []
                
        except Exception as e:
            self.log(f"❌ WAL debug error: {e}")
            return []
            
    def run_comprehensive_test(self):
        """Run comprehensive DELETE sync fix validation"""
        self.log("🧪 DELETE SYNC FIX VALIDATION STARTING")
        self.log("=" * 60)
        
        # Step 1: Health Check
        self.log("📋 Step 1: System Health Check")
        healthy, status = self.check_system_health()
        if not healthy:
            self.log("❌ System not healthy enough for testing")
            return False
            
        healthy_instances = status.get('healthy_instances', 0)
        self.log(f"✅ System healthy: {healthy_instances}/2 instances ready")
        
        # Step 2: Create Test Collection
        self.log("\n📋 Step 2: Create Test Collection")
        collection_name = f"{self.test_session}_DELETE_TEST_{uuid.uuid4().hex[:8]}"
        
        if not self.create_test_collection(collection_name):
            self.log("❌ Test failed: Could not create collection")
            return False
            
        # Step 3: Verify Creation Sync
        self.log("\n📋 Step 3: Verify Collection Creation Sync")
        time.sleep(5)  # Brief wait for creation sync
        creation_state = self.verify_collection_state(collection_name)
        
        primary_exists = creation_state.get('primary', {}).get('exists', False)
        replica_exists = creation_state.get('replica', {}).get('exists', False)
        
        if not (primary_exists and replica_exists):
            self.log("❌ Test failed: Collection not properly synced after creation")
            return False
            
        self.log("✅ Collection creation synced to both instances")
        
        # Step 4: Wait for System Stability
        self.log("\n📋 Step 4: Wait for System Stability")
        time.sleep(10)  # Wait for any background sync to complete
        
        # Step 5: Delete Collection
        self.log("\n📋 Step 5: Delete Collection via Load Balancer")
        delete_success, delete_reason = self.delete_test_collection(collection_name)
        
        if not delete_success:
            if delete_reason == "infrastructure_issue":
                self.log("⚠️ DELETE failed due to infrastructure issue - checking manual deletion")
                # Try manual deletion from primary
                try:
                    manual_response = requests.delete(
                        f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                        timeout=10
                    )
                    self.log(f"🔧 Manual primary deletion: HTTP {manual_response.status_code}")
                except Exception as e:
                    self.log(f"❌ Manual deletion failed: {e}")
                    return False
            else:
                self.log(f"❌ Test failed: DELETE operation failed ({delete_reason})")
                return False
                
        # Step 6: Wait for DELETE Sync
        self.log("\n📋 Step 6: Wait for DELETE Sync Completion")
        self.wait_for_sync(60)
        
        # Step 7: Verify DELETE Sync (The Critical Test!)
        self.log("\n📋 Step 7: Verify DELETE Sync on Both Instances")
        self.log("🔍 THIS IS THE CRITICAL TEST - Does our bug fix work?")
        
        final_state = self.verify_collection_state(collection_name)
        
        primary_still_exists = final_state.get('primary', {}).get('exists', True)
        replica_still_exists = final_state.get('replica', {}).get('exists', True)
        
        # Step 8: Check WAL Debug Information
        self.log("\n📋 Step 8: Check WAL Debug Information")
        wal_deletes = self.check_wal_debug_info(collection_name)
        
        # Step 9: Analyze Results
        self.log("\n📋 Step 9: Test Results Analysis")
        
        if not primary_still_exists and not replica_still_exists:
            self.log("🎉 DELETE SYNC FIX VALIDATION: PASSED!")
            self.log("    ✅ Collection properly deleted from PRIMARY")
            self.log("    ✅ Collection properly deleted from REPLICA")
            self.log("    ✅ Our bug fix is working correctly!")
            
            if wal_deletes:
                synced_instances = wal_deletes[0].get('synced_instances', [])
                if 'primary' in synced_instances and 'replica' in synced_instances:
                    self.log("    ✅ WAL correctly reports sync to both instances")
                else:
                    self.log(f"    ⚠️ WAL sync report: {synced_instances}")
            
            self.log("\n🎯 CRITICAL BUG FIX VALIDATION: SUCCESS")
            return True
            
        else:
            self.log("❌ DELETE SYNC FIX VALIDATION: FAILED!")
            if primary_still_exists:
                self.log("    ❌ Collection still exists on PRIMARY")
            if replica_still_exists:
                self.log("    ❌ Collection still exists on REPLICA")
                
            self.log("    🔍 Our bug fix may not be working as expected")
            
            if wal_deletes:
                synced_instances = wal_deletes[0].get('synced_instances', [])
                self.log(f"    📋 WAL claims synced to: {synced_instances}")
                
            return False
            
    def cleanup(self):
        """Clean up test collections"""
        if self.test_collections:
            self.log(f"\n🧹 Cleaning up {len(self.test_collections)} test collections...")
            for collection_name in self.test_collections:
                try:
                    # Try both load balancer and direct instance cleanup
                    requests.delete(f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}", timeout=5)
                    requests.delete(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}", timeout=5)
                    requests.delete(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}", timeout=5)
                except:
                    pass  # Ignore cleanup errors

def main():
    validator = DeleteSyncFixValidator()
    
    try:
        success = validator.run_comprehensive_test()
        
        if success:
            print("\n🎉 DELETE SYNC FIX VALIDATION: COMPLETE SUCCESS!")
            print("   The critical collection name vs UUID bug has been resolved!")
        else:
            print("\n❌ DELETE SYNC FIX VALIDATION: ISSUES DETECTED")
            print("   The bug fix may need additional work")
            
        return success
        
    finally:
        validator.cleanup()

if __name__ == "__main__":
    main() 