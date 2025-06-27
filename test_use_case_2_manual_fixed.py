#!/usr/bin/env python3

# FIXED VERSION: This test will actually FAIL when there are real system issues
# Key changes: Remove forgiving validation, enforce strict recovery requirements

import sys
import time
import requests
import argparse
import subprocess
from datetime import datetime
from enhanced_verification_base import EnhancedVerificationBase

class UseCase2TesterFixed(EnhancedVerificationBase):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url.rstrip('/')
        self.session_id = f"UC2_MANUAL_{int(time.time())}"
        self.test_collections = []
        self.test_results = {}
        self.documents_added_during_failure = {}
        self.start_time = None
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"

    def validate_system_integrity_strict(self, test_name):
        """
        STRICT system integrity validation - FAILS if issues aren't resolved within timeout
        """
        print(f"   🔍 VALIDATING: System integrity for {test_name} (STRICT MODE)")
        
        # Check for stuck transactions FIRST
        try:
            tx_response = requests.get(f"{self.base_url}/admin/transaction_safety_status", timeout=10)
            if tx_response.status_code == 200:
                tx_data = tx_response.json()
                
                # CRITICAL: Check for stuck transactions in ATTEMPTING status
                stuck_transactions = 0
                for tx in tx_data.get('recent_transactions', {}).get('by_status', []):
                    if tx['status'] == 'ATTEMPTING':
                        stuck_transactions = tx['count']
                        
                if stuck_transactions > 0:
                    return self.fail(test_name, f"CRITICAL: {stuck_transactions} transactions stuck in ATTEMPTING status", 
                                   "This indicates system cannot complete transactions - FAILURE")
                                   
        except Exception as e:
            return self.fail(test_name, "Cannot check transaction status", str(e))
        
        # Wait for recovery systems with STRICT timeout enforcement
        max_wait_time = 90  # seconds
        check_interval = 5
        start_time = time.time()
        
        print(f"   ⏳ Monitoring system for {max_wait_time}s for recovery (STRICT: must complete)")
        
        while time.time() - start_time < max_wait_time:
            pending_issues = []
            
            # Check WAL status
            try:
                wal_status_response = requests.get(f"{self.base_url}/wal/status", timeout=10)
                if wal_status_response.status_code == 200:
                    wal_data = wal_status_response.json()
                    pending_writes = wal_data.get('pending_writes', 0)
                    failed_syncs = wal_data.get('failed_syncs', 0)
                    
                    if pending_writes > 0:
                        pending_issues.append(f"{pending_writes} pending WAL writes")
                    if failed_syncs > 0:  # STRICT: No failed syncs allowed
                        pending_issues.append(f"{failed_syncs} failed WAL syncs")
                        
            except Exception:
                return self.fail(test_name, "Cannot check WAL status", "System monitoring failed")
            
            if not pending_issues:
                print(f"   ✅ System integrity validated - all operations processed")
                return True
            
            remaining_time = max_wait_time - (time.time() - start_time)
            print(f"   ⏳ Waiting for recovery ({remaining_time:.0f}s remaining): {'; '.join(pending_issues)}")
            time.sleep(check_interval)
        
        # STRICT: FAIL if operations not completed within timeout
        return self.fail(test_name, "Recovery timeout reached", "Operations did not complete within 90 seconds - SYSTEM FAILURE")

    def validate_document_sync_strict(self, collection_name, expected_doc_count, test_name):
        """
        STRICT document sync validation - FAILS if sync doesn't complete within timeout
        """
        print(f"   🔍 VALIDATING: Document sync for {test_name} (STRICT MODE)")
        
        max_wait_time = 120  # seconds
        check_interval = 3
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            primary_count = None
            replica_count = None
            
            try:
                # Primary instance - MUST exist by collection name
                primary_response = requests.post(
                    f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                    json={"include": ["documents"]},
                    timeout=10
                )
                if primary_response.status_code == 200:
                    primary_data = primary_response.json()
                    primary_count = len(primary_data.get('documents', []))
                    
                # Replica instance - MUST exist by collection name
                replica_response = requests.post(
                    f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                    json={"include": ["documents"]},
                    timeout=10
                )
                if replica_response.status_code == 200:
                    replica_data = replica_response.json()
                    replica_count = len(replica_data.get('documents', []))
                    
            except Exception as e:
                return self.fail(test_name, "Cannot access instances for validation", str(e))
                
            if primary_count is not None and replica_count is not None:
                if primary_count == replica_count == expected_doc_count:
                    print(f"   ✅ Document sync validated: {primary_count} docs on both instances")
                    return True
                else:
                    remaining_time = max_wait_time - (time.time() - start_time)
                    print(f"   ⏳ Document sync in progress ({remaining_time:.0f}s): Primary: {primary_count}, Replica: {replica_count}, Expected: {expected_doc_count}")
            else:
                remaining_time = max_wait_time - (time.time() - start_time)
                print(f"   ⏳ Waiting for collection access ({remaining_time:.0f}s)...")
                
            time.sleep(check_interval)
        
        # STRICT: FAIL if sync doesn't complete within timeout
        return self.fail(test_name, "Document sync timeout", 
                        f"Documents did not sync to both instances within {max_wait_time} seconds - SYNC FAILURE")

    def verify_data_consistency_strict(self, max_retries=3):
        """
        STRICT data consistency verification - FAILS if data doesn't exist on both instances
        """
        self.log("🔍 Verifying data consistency (STRICT MODE: must exist on both instances)")
        
        for attempt in range(max_retries):
            if attempt > 0:
                self.log(f"🔄 Verification attempt {attempt + 1}/{max_retries} (waiting 30s)...")
                time.sleep(30)
        
            try:
                # STRICT: Collections MUST exist via load balancer
                response = requests.get(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                    timeout=10
                )
                
                if response.status_code != 200:
                    if attempt < max_retries - 1:
                        continue
                    return self.fail("Data Consistency Check", "Cannot access load balancer collections", 
                                   f"HTTP {response.status_code}")
                    
                collections = response.json()
                collection_names = [c['name'] for c in collections]
                found_collections = [name for name in self.test_collections if name in collection_names]
                
                self.log(f"📊 Collection verification (attempt {attempt + 1}/{max_retries}):")
                self.log(f"   Created during failure: {len(self.test_collections)}")
                self.log(f"   Found after recovery: {len(found_collections)}")
                
                # STRICT: ALL collections MUST be found
                collection_consistency = len(found_collections) == len(self.test_collections)
                
                if not collection_consistency:
                    missing_collections = [name for name in self.test_collections if name not in collection_names]
                    if attempt < max_retries - 1:
                        self.log(f"   ⚠️ Missing collections: {missing_collections} - retrying...")
                        continue
                    else:
                        return self.fail("Data Consistency Check", "Collections missing after recovery", 
                                       f"Missing: {missing_collections}")
                
                # STRICT: Verify collections exist on BOTH instances directly
                mappings = self.get_collection_mappings()
                
                for collection_name in found_collections:
                    # Find UUIDs for direct instance validation
                    primary_uuid = None
                    replica_uuid = None
                    
                    for mapping in mappings:
                        if mapping.get('collection_name') == collection_name:
                            primary_uuid = mapping.get('primary_collection_id')
                            replica_uuid = mapping.get('replica_collection_id')
                            break
                    
                    if not primary_uuid or not replica_uuid:
                        if attempt < max_retries - 1:
                            self.log(f"   ⚠️ Missing UUIDs for {collection_name} - retrying...")
                            continue
                        else:
                            return self.fail("Data Consistency Check", f"No UUID mapping for {collection_name}", 
                                           "Recovery incomplete - collections not properly synced")
                    
                    # STRICT: Verify collection exists on primary
                    primary_exists = self.check_collection_exists_on_instance(self.primary_url, primary_uuid)
                    if not primary_exists:
                        if attempt < max_retries - 1:
                            self.log(f"   ⚠️ Collection {collection_name} not on primary - retrying...")
                            continue
                        else:
                            return self.fail("Data Consistency Check", f"Collection {collection_name} missing from primary", 
                                           "Recovery failed - data not synced to primary")
                    
                    # STRICT: Verify collection exists on replica
                    replica_exists = self.check_collection_exists_on_instance(self.replica_url, replica_uuid)
                    if not replica_exists:
                        if attempt < max_retries - 1:
                            self.log(f"   ⚠️ Collection {collection_name} not on replica - retrying...")
                            continue
                        else:
                            return self.fail("Data Consistency Check", f"Collection {collection_name} missing from replica", 
                                           "Recovery failed - data not synced to replica")
                    
                    self.log(f"   ✅ Collection {collection_name}: Verified on both instances")
                
                self.log(f"🎯 STRICT data consistency: ✅ Complete (all collections on both instances)")
                return True
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    self.log(f"❌ Verification error (attempt {attempt + 1}/{max_retries}): {e}")
                    continue
                else:
                    return self.fail("Data Consistency Check", "Verification failed with exception", str(e))
                    
        return self.fail("Data Consistency Check", "All verification attempts failed", "System recovery incomplete")

    def check_collection_exists_on_instance(self, instance_url, collection_uuid):
        """Check if collection exists on specific instance by UUID"""
        try:
            response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}",
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False

    def fail(self, test, reason, details=""):
        """Mark a test as failed with detailed information"""
        print(f"❌ PRODUCTION FAILURE: {test}")
        print(f"   Reason: {reason}")
        if details:
            print(f"   Details: {details}")
        return False

    def test_operations_during_failure(self):
        """Test operations during primary failure with strict validation"""
        self.log("🧪 Testing operations during primary failure (STRICT MODE)...")
        
        success_count = 0
        total_tests = 4
        
        # Test 1: Collection Creation
        test_name = "collection_creation"
        self.log("Test 1: Collection Creation")
        
        collection_name = f"{self.session_id}_CREATE_TEST"
        try:
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name},
                timeout=15
            )
            
            if response.status_code == 200:
                self.test_collections.append(collection_name)
                self.test_results[test_name] = {'collections': [collection_name], 'success': True}
                success_count += 1
                self.log(f"✅ Collection created: {collection_name}")
            else:
                self.test_results[test_name] = {'collections': [], 'success': False}
                self.log(f"❌ Collection creation failed: {response.status_code}")
                
        except Exception as e:
            self.test_results[test_name] = {'collections': [], 'success': False}
            self.log(f"❌ Collection creation error: {e}")
        
        # Test 2: Document Addition
        test_name = "document_addition"
        self.log("Test 2: Document Addition")
        
        if self.test_collections:
            try:
                collection_name = self.test_collections[0]
                doc_id = f"doc_{self.session_id}"
                
                response = requests.post(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                    json={
                        "documents": ["Test document during primary failure"],
                        "metadatas": [{"test_type": "primary_down", "session": self.session_id}],
                        "ids": [doc_id],
                        "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]]
                    },
                    timeout=15
                )
                
                if response.status_code == 201:
                    self.test_results[test_name] = {'collections': [], 'success': True}
                    success_count += 1
                    self.log(f"✅ Document added: {doc_id}")
                    
                    # Track for verification
                    if collection_name not in self.documents_added_during_failure:
                        self.documents_added_during_failure[collection_name] = []
                    self.documents_added_during_failure[collection_name].append({
                        'id': doc_id,
                        'expected_count': 1
                    })
                else:
                    self.test_results[test_name] = {'collections': [], 'success': False}
                    self.log(f"❌ Document addition failed: {response.status_code}")
                    
            except Exception as e:
                self.test_results[test_name] = {'collections': [], 'success': False}
                self.log(f"❌ Document addition error: {e}")
        else:
            self.test_results[test_name] = {'collections': [], 'success': False}
            self.log("❌ No collection available for document test")
        
        # Test 3: Additional Collection
        test_name = "additional_collection"
        self.log("Test 3: Additional Collection Creation")
        
        additional_collection = f"{self.session_id}_ADDITIONAL"
        try:
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": additional_collection},
                timeout=15
            )
            
            if response.status_code == 200:
                self.test_collections.append(additional_collection)
                self.test_results[test_name] = {'collections': [additional_collection], 'success': True}
                success_count += 1
                self.log(f"✅ Additional collection created: {additional_collection}")
            else:
                self.test_results[test_name] = {'collections': [], 'success': False}
                self.log(f"❌ Additional collection failed: {response.status_code}")
                
        except Exception as e:
            self.test_results[test_name] = {'collections': [], 'success': False}
            self.log(f"❌ Additional collection error: {e}")
        
        # Test 4: System Health Check
        test_name = "health_check"
        self.log("Test 4: System Health During Failure")
        
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                healthy_instances = status.get('healthy_instances', 0)
                if healthy_instances >= 1:  # At least replica should be healthy
                    self.test_results[test_name] = {'collections': [], 'success': True}
                    success_count += 1
                    self.log(f"✅ System health check: {healthy_instances}/2 instances healthy")
                else:
                    self.test_results[test_name] = {'collections': [], 'success': False}
                    self.log(f"❌ System unhealthy: {healthy_instances}/2 instances")
            else:
                self.test_results[test_name] = {'collections': [], 'success': False}
                self.log(f"❌ Health check failed: {response.status_code}")
                
        except Exception as e:
            self.test_results[test_name] = {'collections': [], 'success': False}
            self.log(f"❌ Health check error: {e}")
        
        # STRICT: System integrity must pass
        if not self.validate_system_integrity_strict("Operations During Failure"):
            return 0, total_tests  # Fail all tests if system integrity compromised
        
        # STRICT: Document sync must complete if documents were added
        if self.documents_added_during_failure:
            collection_name = list(self.documents_added_during_failure.keys())[0]
            expected_docs = len(self.documents_added_during_failure[collection_name])
            if not self.validate_document_sync_strict(collection_name, expected_docs, "Document Operations"):
                return 0, total_tests  # Fail all tests if document sync failed
        
        self.log(f"📊 Operations during failure: {success_count}/{total_tests} successful ({success_count/total_tests*100:.1f}%)")
        return success_count, total_tests

    def run_complete_test_cycle(self):
        """Run complete test cycle with strict validation"""
        self.start_time = time.time()
        
        print("="*80)
        print("🚀 USE CASE 2: Primary Instance Down - STRICT VALIDATION MODE")
        print("="*80)
        print("⚠️  THIS VERSION WILL FAIL WHEN THERE ARE REAL ISSUES")
        print("⚠️  (Unlike the original which was too forgiving)")
        print("="*80)
        
        # Initial health check
        self.log("📋 Step 1: Initial System Health Check")
        initial_status = self.check_system_health()
        if not initial_status or initial_status.get('healthy_instances', 0) != 2:
            self.log("❌ System not ready for testing", "ERROR")
            return False
        
        # Manual primary suspension
        input("\n🚨 SUSPEND PRIMARY INSTANCE VIA RENDER DASHBOARD - Press Enter when done...")
        
        # Verify primary is down
        self.log("📋 Verifying primary suspension...")
        time.sleep(10)
        
        for attempt in range(6):
            status = self.check_system_health()
            if status and not status.get('instances', [{}])[0].get('healthy', True):
                self.log("✅ Primary failure detected")
                break
            if attempt == 5:
                return self.fail("Primary Suspension", "Primary not detected as down after 60 seconds", 
                               "Please ensure primary is properly suspended")
            time.sleep(10)
        
        # Test operations during failure
        self.log("📋 Testing operations during failure...")
        success_count, total_tests = self.test_operations_during_failure()
        
        # Manual primary recovery
        input("\n🚨 RESUME PRIMARY INSTANCE VIA RENDER DASHBOARD - Press Enter when done...")
        
        # Wait for recovery (strict timeout)
        self.log("📋 Waiting for recovery (STRICT: must complete in 5 minutes)...")
        start_time = time.time()
        timeout = 300  # 5 minutes strict timeout
        
        while time.time() - start_time < timeout:
            status = self.check_system_health()
            if status:
                healthy = status.get('healthy_instances', 0)
                pending = status.get('unified_wal', {}).get('pending_writes', 0)
                
                if healthy == 2 and pending == 0:
                    self.log("✅ Recovery complete")
                    break
                    
                self.log(f"⏳ Recovery in progress: {healthy}/2 healthy, {pending} pending")
            time.sleep(15)
        else:
            return self.fail("Recovery", "Recovery did not complete within 5 minutes", "SYSTEM FAILURE")
        
        # Strict data consistency verification
        self.log("📋 Verifying data consistency (STRICT MODE)...")
        consistency_ok = self.verify_data_consistency_strict()
        
        # Determine overall result (STRICT)
        overall_test_success = success_count == total_tests and consistency_ok
        
        # Summary
        total_time = time.time() - self.start_time
        print("\n" + "="*80)
        print("📊 USE CASE 2 TESTING SUMMARY (STRICT MODE)")
        print("="*80)
        print(f"⏱️  Total test time: {total_time/60:.1f} minutes")
        print(f"🧪 Operations during failure: {success_count}/{total_tests} successful")
        print(f"📊 Data consistency: {'✅ Complete' if consistency_ok else '❌ FAILED'}")
        
        if overall_test_success:
            print("\n🎉 USE CASE 2: ✅ SUCCESS - All tests passed with strict validation!")
            return True
        else:
            print("\n❌ USE CASE 2: FAILED - System has real issues that need fixing")
            print("🔒 Test data preserved for debugging")
            return False

    def check_system_health(self):
        """Check system health"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

def main():
    parser = argparse.ArgumentParser(description='USE CASE 2: STRICT validation version')
    parser.add_argument('--url', required=True, help='Load balancer URL')
    args = parser.parse_args()
    
    tester = UseCase2TesterFixed(args.url)
    success = tester.run_complete_test_cycle()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 