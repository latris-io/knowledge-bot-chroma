#!/usr/bin/env python3
"""
Resilient DELETE Sync Test
Tests DELETE sync functionality even during infrastructure failures
This validates our DELETE sync fix under real-world conditions
"""

import requests
import time
import uuid
import json
from datetime import datetime
from logging_config import setup_test_logging

class ResilientDeleteSyncTest:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.test_session = f"RESILIENT_DELETE_{int(time.time())}"
        self.logger = setup_test_logging("resilient_delete_sync")
        self.test_collections = []
        
    def log(self, message):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        self.logger.info(message)
    
    def get_system_status(self):
        """Get detailed system status"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                self.log(f"❌ Status check failed: HTTP {response.status_code}")
                return None
        except Exception as e:
            self.log(f"❌ Status check error: {e}")
            return None
    
    def create_test_collection_when_healthy(self):
        """Create test collection, waiting for system to be healthy if needed"""
        collection_name = f"{self.test_session}_TEST_{uuid.uuid4().hex[:8]}"
        
        # Wait for system to be healthy enough for creation
        max_attempts = 6  # 60 seconds total
        for attempt in range(max_attempts):
            status = self.get_system_status()
            if status:
                healthy = status.get('healthy_instances', 0)
                if healthy >= 1:  # At least one instance healthy for creation
                    break
            
            if attempt < max_attempts - 1:
                self.log(f"⏳ Waiting for healthy instance... attempt {attempt + 1}/{max_attempts}")
                time.sleep(10)
            else:
                self.log("❌ No healthy instances available for collection creation")
                return None
        
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
    
    def attempt_delete_with_retry(self, collection_name, max_retries=3):
        """Attempt DELETE with retry logic for infrastructure issues"""
        for attempt in range(max_retries):
            try:
                self.log(f"🗑️ DELETE attempt {attempt + 1}/{max_retries}")
                
                response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                    timeout=15
                )
                
                self.log(f"   Response: HTTP {response.status_code} in {response.elapsed.total_seconds():.3f}s")
                
                if response.status_code in [200, 204]:
                    self.log("   ✅ DELETE successful")
                    return True
                elif response.status_code == 503:
                    self.log("   ⚠️ Service temporarily unavailable (503)")
                    if attempt < max_retries - 1:
                        self.log("   ⏳ Retrying in 15 seconds...")
                        time.sleep(15)
                    continue
                else:
                    self.log(f"   ❌ DELETE failed with HTTP {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(10)
                    continue
                    
            except Exception as e:
                self.log(f"   ❌ DELETE error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                continue
        
        self.log(f"❌ DELETE failed after {max_retries} attempts")
        return False
    
    def wait_for_infrastructure_recovery(self, max_wait=180):
        """Wait for infrastructure to recover after DELETE operation"""
        self.log(f"⏳ Monitoring infrastructure recovery (max {max_wait}s)...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            status = self.get_system_status()
            if status:
                healthy = status.get('healthy_instances', 0)
                total = status.get('total_instances', 2)
                
                self.log(f"   System status: {healthy}/{total} instances healthy")
                
                if healthy == total:  # Both instances healthy
                    self.log(f"✅ Infrastructure recovered - both instances healthy")
                    return True
                elif healthy >= 1:
                    self.log(f"   🔄 Partial recovery - waiting for full recovery...")
            
            time.sleep(15)
        
        self.log(f"⏰ Infrastructure recovery timeout after {max_wait}s")
        return False
    
    def wait_for_sync_completion(self, max_wait=120):
        """Wait for WAL sync to complete"""
        self.log(f"⏳ Waiting for WAL sync completion (max {max_wait}s)...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{self.base_url}/wal/status", timeout=10)
                if response.status_code == 200:
                    wal_status = response.json()
                    pending = wal_status.get('wal_system', {}).get('pending_writes', -1)
                    
                    elapsed = int(time.time() - start_time)
                    if pending == 0:
                        self.log(f"✅ WAL sync completed in {elapsed}s (0 pending writes)")
                        return True
                    else:
                        self.log(f"   WAL sync in progress: {pending} pending writes ({elapsed}s elapsed)")
                        
                time.sleep(15)
            except Exception as e:
                self.log(f"   WAL status check error: {e}")
                time.sleep(15)
        
        self.log(f"⏰ WAL sync timeout after {max_wait}s")
        return False
    
    def verify_delete_sync_on_both_instances(self, collection_name):
        """Verify DELETE sync worked on both instances"""
        instances = [
            ("Primary", "https://chroma-primary.onrender.com"),
            ("Replica", "https://chroma-replica.onrender.com")
        ]
        
        results = {}
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
                        self.log(f"   ❌ {instance_name}: Collection still exists (DELETE sync failed)")
                        results[instance_name.lower()] = False
                    else:
                        self.log(f"   ✅ {instance_name}: Collection properly deleted")
                        results[instance_name.lower()] = True
                else:
                    self.log(f"   ⚠️ {instance_name}: Cannot verify (HTTP {response.status_code})")
                    results[instance_name.lower()] = None
                    
            except Exception as e:
                self.log(f"   ❌ {instance_name}: Verification error - {e}")
                results[instance_name.lower()] = None
        
        return results
    
    def check_wal_debug_for_delete_operations(self):
        """Check WAL debug information for our DELETE operations"""
        try:
            response = requests.get(f"{self.base_url}/admin/wal_debug", timeout=10)
            if response.status_code == 200:
                debug_info = response.json()
                delete_ops = debug_info.get('delete_operations', [])
                
                self.log(f"🔍 WAL Debug: Found {len(delete_ops)} recent DELETE operations")
                
                # Look for our test session operations
                session_deletes = [op for op in delete_ops if self.test_session in op.get('collection_id', '')]
                if session_deletes:
                    self.log(f"   📋 Found {len(session_deletes)} DELETE operations from this test:")
                    for op in session_deletes:
                        self.log(f"      DELETE {op['write_id']}: {op['collection_id']}")
                        self.log(f"      Status: {op['status']}, Target: {op['target_instance']}")
                        self.log(f"      Synced instances: {op['synced_instances']}")
                        
                        # Check if this operation demonstrates our fix working
                        if op['status'] == 'synced' and op['synced_instances']:
                            try:
                                synced_list = json.loads(op['synced_instances']) if isinstance(op['synced_instances'], str) else op['synced_instances']
                                if isinstance(synced_list, list) and len(synced_list) == 2:
                                    self.log(f"      🎉 SUCCESS: DELETE synced to both instances: {synced_list}")
                                else:
                                    self.log(f"      ⚠️ PARTIAL: DELETE synced to: {synced_list}")
                            except:
                                self.log(f"      ⚠️ UNKNOWN: Could not parse synced_instances")
                else:
                    self.log(f"   📋 No DELETE operations found for session {self.test_session}")
                
                return True
            else:
                self.log(f"❌ WAL debug failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ WAL debug error: {e}")
            return False
    
    def run_resilient_test(self):
        """Run resilient DELETE sync test that handles infrastructure failures"""
        self.log("🛡️ RESILIENT DELETE SYNC TEST STARTING")
        self.log("=" * 60)
        
        # Step 1: Create collection when system is healthy
        self.log("📋 Step 1: Create Test Collection (Wait for Health)")
        collection_name = self.create_test_collection_when_healthy()
        if not collection_name:
            self.log("❌ TEST FAILED: Could not create test collection")
            return False
        
        # Step 2: Wait for creation to propagate
        self.log("\n📋 Step 2: Wait for Creation Propagation")
        time.sleep(10)
        
        # Step 3: Attempt DELETE (may fail due to infrastructure issues)
        self.log("\n📋 Step 3: Attempt DELETE with Retry Logic")
        delete_success = self.attempt_delete_with_retry(collection_name)
        
        if not delete_success:
            self.log("❌ TEST FAILED: DELETE operation failed completely")
            return False
        
        # Step 4: Wait for infrastructure recovery
        self.log("\n📋 Step 4: Wait for Infrastructure Recovery")
        recovery_success = self.wait_for_infrastructure_recovery()
        
        # Step 5: Wait for sync completion
        self.log("\n📋 Step 5: Wait for DELETE Sync Completion")
        sync_completed = self.wait_for_sync_completion()
        
        # Step 6: Verify DELETE sync on both instances
        self.log("\n📋 Step 6: Verify DELETE Sync on Both Instances")
        sync_results = self.verify_delete_sync_on_both_instances(collection_name)
        
        primary_synced = sync_results.get('primary', False)
        replica_synced = sync_results.get('replica', False)
        
        # Step 7: Check WAL debug information
        self.log("\n📋 Step 7: WAL Debug Analysis")
        self.check_wal_debug_for_delete_operations()
        
        # Step 8: Final results
        self.log("\n📋 Step 8: Test Results Analysis")
        
        # Success criteria: Both instances should have collection deleted
        if primary_synced == True and replica_synced == True:
            self.log("🎉 RESILIENT DELETE SYNC TEST: PASSED")
            self.log("   ✅ DELETE operation succeeded despite infrastructure issues")
            self.log("   ✅ DELETE sync worked correctly on both instances")
            self.log("   ✅ Our DELETE sync fix is working correctly!")
            return True
        elif primary_synced == False or replica_synced == False:
            self.log("❌ RESILIENT DELETE SYNC TEST: FAILED")
            self.log("   ❌ DELETE sync issue detected:")
            if primary_synced == False:
                self.log("      - Collection still exists on PRIMARY")
            if replica_synced == False:
                self.log("      - Collection still exists on REPLICA") 
            self.log("   🔧 DELETE sync fix may need additional work")
            return False
        else:
            self.log("⚠️ RESILIENT DELETE SYNC TEST: INCONCLUSIVE")
            self.log("   ⚠️ Could not verify DELETE sync due to infrastructure issues")
            self.log("   🔄 Test should be re-run when infrastructure is stable")
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
    tester = ResilientDeleteSyncTest()
    
    try:
        success = tester.run_resilient_test()
        
        print("\n" + "=" * 60)
        if success:
            print("🎉 DELETE SYNC FIX VALIDATION: PASSED")
            print("The DELETE sync fix works correctly even under infrastructure stress!")
        elif success is False:
            print("❌ DELETE SYNC FIX VALIDATION: FAILED") 
            print("The DELETE sync issue may still exist - review logs for details")
        else:
            print("⚠️ DELETE SYNC FIX VALIDATION: INCONCLUSIVE")
            print("Infrastructure issues prevented complete validation")
        print("=" * 60)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n⏸️ Test interrupted by user")
        return 2
    except Exception as e:
        print(f"\n💥 Test error: {e}")
        return 3
    finally:
        tester.cleanup()

if __name__ == "__main__":
    exit(main()) 