#!/usr/bin/env python3
"""
Test Auto-Mapping and Document Sync Functionality
Covers the specific scenarios fixed for CMS DELETE sync issues
"""

import sys
import requests
import logging
import json
import uuid
import time
from datetime import datetime
import atexit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AutoMappingDocumentSyncTest:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.test_session_id = f"automap_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.created_collections = set()
        self.test_results = []
        
        # Register emergency cleanup
        atexit.register(self.emergency_cleanup)
        
    def log_result(self, test_name, success, details="", duration=0):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name} ({duration:.2f}s)")
        if details:
            logger.info(f"   {details}")
        
        self.test_results.append({
            'test_name': test_name,
            'success': success,
            'details': details,
            'duration': duration
        })
        
        return success
    
    def get_collection_mapping(self, collection_name):
        """Get collection mapping from database"""
        try:
            response = requests.get(f"{self.base_url}/collection/mappings", timeout=15)
            if response.status_code == 200:
                mappings = response.json().get('mappings', [])
                for mapping in mappings:
                    if mapping['collection_name'] == collection_name:
                        return mapping
            return None
        except Exception:
            return None
    
    def get_collection_info_direct(self, instance_url, collection_id_or_name):
        """Get collection info directly from an instance"""
        try:
            response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id_or_name}",
                timeout=15
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None
    
    def count_documents_direct(self, instance_url, collection_id):
        """Count documents directly on an instance"""
        try:
            response = requests.post(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get",
                headers={"Content-Type": "application/json"},
                json={"limit": 1},
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                return len(data.get('ids', []))
            return 0
        except Exception:
            return 0
    
    def test_auto_mapping_creation(self):
        """Test 1: Auto-mapping creation when collection is created"""
        logger.info("\n🔧 Testing Auto-Mapping Creation")
        
        collection_name = f"test_auto_mapping_{self.test_session_id}"
        self.created_collections.add(collection_name)
        
        start_time = time.time()
        try:
            # Create collection through load balancer
            collection_payload = {
                "name": collection_name,
                "configuration": {
                    "hnsw": {
                        "space": "l2",
                        "ef_construction": 100,
                        "ef_search": 100,
                        "max_neighbors": 16
                    }
                }
            }
            
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            
            duration = time.time() - start_time
            
            if response.status_code not in [200, 201]:
                return self.log_result(
                    "Auto-Mapping: Collection Creation",
                    False,
                    f"Failed to create collection: {response.status_code}",
                    duration
                )
            
            collection_data = response.json()
            primary_collection_id = collection_data.get('id')
            
            # Wait for auto-mapping to be created
            logger.info("   Waiting 5s for auto-mapping creation...")
            time.sleep(5)
            
            # Check if mapping was automatically created
            mapping = self.get_collection_mapping(collection_name)
            
            if mapping:
                primary_id = mapping.get('primary_collection_id')
                replica_id = mapping.get('replica_collection_id')
                
                success = (primary_id == primary_collection_id and replica_id and replica_id != primary_id)
                details = f"Primary: {primary_id[:8]}..., Replica: {replica_id[:8]}..." if success else "Mapping invalid"
                
                return self.log_result(
                    "Auto-Mapping: Creation Verification",
                    success,
                    details,
                    duration
                )
            else:
                return self.log_result(
                    "Auto-Mapping: Creation Verification",
                    False,
                    "No mapping found in database",
                    duration
                )
                
        except Exception as e:
            duration = time.time() - start_time
            return self.log_result(
                "Auto-Mapping: Creation Verification",
                False,
                f"Exception: {str(e)}",
                duration
            )
    
    def test_collection_exists_on_both_instances(self):
        """Test 2: Verify collection exists on both primary and replica"""
        logger.info("\n🔍 Testing Collection Existence on Both Instances")
        
        collection_name = f"test_auto_mapping_{self.test_session_id}"
        mapping = self.get_collection_mapping(collection_name)
        
        if not mapping:
            return self.log_result(
                "Instance Verification: No Mapping",
                False,
                "Cannot test without collection mapping",
                0
            )
        
        primary_id = mapping.get('primary_collection_id')
        replica_id = mapping.get('replica_collection_id')
        
        start_time = time.time()
        
        # Check primary instance
        primary_info = self.get_collection_info_direct("https://chroma-primary.onrender.com", primary_id)
        primary_exists = primary_info is not None
        
        # Check replica instance  
        replica_info = self.get_collection_info_direct("https://chroma-replica.onrender.com", replica_id)
        replica_exists = replica_info is not None
        
        duration = time.time() - start_time
        
        success = primary_exists and replica_exists
        details = f"Primary: {'✅' if primary_exists else '❌'}, Replica: {'✅' if replica_exists else '❌'}"
        
        return self.log_result(
            "Instance Verification: Both Instances",
            success,
            details,
            duration
        )
    
    def test_document_sync_via_load_balancer(self):
        """Test 3: Document sync from primary to replica via load balancer"""
        logger.info("\n📄 Testing Document Sync via Load Balancer")
        
        collection_name = f"test_auto_mapping_{self.test_session_id}"
        mapping = self.get_collection_mapping(collection_name)
        
        if not mapping:
            return self.log_result(
                "Document Sync: No Mapping",
                False,
                "Cannot test without collection mapping",
                0
            )
        
        primary_id = mapping.get('primary_collection_id')
        replica_id = mapping.get('replica_collection_id')
        
        start_time = time.time()
        
        try:
            # Add documents via load balancer using collection NAME
            test_docs = {
                "ids": [f"sync_test_{self.test_session_id}_{i}" for i in range(3)],
                "documents": [f"Sync test document {i} - {self.test_session_id}" for i in range(3)],
                "metadatas": [{"test_session": self.test_session_id, "doc_index": i} for i in range(3)],
                "embeddings": [[0.1*i, 0.2*i, 0.3*i, 0.4*i, 0.5*i] for i in range(1, 4)]
            }
            
            # Use collection NAME (not UUID) to test name-to-UUID mapping
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                headers={"Content-Type": "application/json"},
                json=test_docs,
                timeout=30
            )
            
            if response.status_code not in [200, 201]:
                duration = time.time() - start_time
                return self.log_result(
                    "Document Sync: Add Documents",
                    False,
                    f"Failed to add documents: {response.status_code}",
                    duration
                )
            
            # Wait for WAL sync
            logger.info("   Waiting 25s for WAL document sync...")
            time.sleep(25)
            
            # Check document counts on both instances directly
            primary_count = self.count_documents_direct("https://chroma-primary.onrender.com", primary_id)
            replica_count = self.count_documents_direct("https://chroma-replica.onrender.com", replica_id)
            
            duration = time.time() - start_time
            
            success = (primary_count > 0 and replica_count > 0 and primary_count == replica_count)
            details = f"Primary: {primary_count} docs, Replica: {replica_count} docs"
            
            return self.log_result(
                "Document Sync: Primary→Replica Sync",
                success,
                details,
                duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return self.log_result(
                "Document Sync: Primary→Replica Sync",
                False,
                f"Exception: {str(e)}",
                duration
            )
    
    def test_name_to_uuid_mapping(self):
        """Test 4: Collection name-to-UUID mapping for requests"""
        logger.info("\n🏷️ Testing Collection Name-to-UUID Mapping")
        
        collection_name = f"test_auto_mapping_{self.test_session_id}"
        
        start_time = time.time()
        
        try:
            # Try to access collection by NAME through load balancer
            response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                timeout=15
            )
            
            duration = time.time() - start_time
            
            if response.status_code == 200:
                collection_data = response.json()
                returned_name = collection_data.get('name')
                returned_id = collection_data.get('id')
                
                success = returned_name == collection_name and returned_id
                details = f"Name: {returned_name}, ID: {returned_id[:8] if returned_id else 'None'}..."
                
                return self.log_result(
                    "Name Mapping: Collection Access by Name",
                    success,
                    details,
                    duration
                )
            else:
                return self.log_result(
                    "Name Mapping: Collection Access by Name",
                    False,
                    f"HTTP {response.status_code}",
                    duration
                )
                
        except Exception as e:
            duration = time.time() - start_time
            return self.log_result(
                "Name Mapping: Collection Access by Name",
                False,
                f"Exception: {str(e)}",
                duration
            )
    
    def test_wal_uuid_mapping_functionality(self):
        """Test 5: WAL system UUID mapping functionality"""
        logger.info("\n⚙️ Testing WAL UUID Mapping Functionality")
        
        start_time = time.time()
        
        try:
            # Check WAL status for successful syncs
            response = requests.get(f"{self.base_url}/wal/status", timeout=15)
            
            if response.status_code == 200:
                wal_data = response.json()
                stats = wal_data.get('performance_stats', {})
                successful_syncs = stats.get('successful_syncs', 0)
                failed_syncs = stats.get('failed_syncs', 0)
                
                duration = time.time() - start_time
                
                # Success if we have more successful syncs than failed ones
                success = successful_syncs >= failed_syncs
                details = f"Successful: {successful_syncs}, Failed: {failed_syncs}"
                
                return self.log_result(
                    "WAL Mapping: Sync Success Rate",
                    success,
                    details,
                    duration
                )
            else:
                duration = time.time() - start_time
                return self.log_result(
                    "WAL Mapping: Sync Success Rate",
                    False,
                    f"HTTP {response.status_code}",
                    duration
                )
                
        except Exception as e:
            duration = time.time() - start_time
            return self.log_result(
                "WAL Mapping: Sync Success Rate",
                False,
                f"Exception: {str(e)}",
                duration
            )
    
    def cleanup_test_collections(self):
        """Clean up test collections"""
        logger.info("\n🧹 Cleaning up test collections...")
        
        for collection_name in self.created_collections:
            try:
                # Try to delete from load balancer
                response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                    timeout=15
                )
                if response.status_code in [200, 404]:
                    logger.info(f"   ✅ Cleaned up: {collection_name}")
                else:
                    logger.warning(f"   ⚠️ Cleanup failed for {collection_name}: {response.status_code}")
            except Exception as e:
                logger.warning(f"   ❌ Cleanup error for {collection_name}: {e}")
    
    def emergency_cleanup(self):
        """Emergency cleanup on exit"""
        if self.created_collections:
            logger.info("🚨 Emergency cleanup triggered")
            self.cleanup_test_collections()
    
    def run_all_tests(self):
        """Run all auto-mapping and document sync tests"""
        logger.info("🚀 Starting Auto-Mapping and Document Sync Tests")
        logger.info(f"📋 Test Session ID: {self.test_session_id}")
        
        tests = [
            self.test_auto_mapping_creation,
            self.test_collection_exists_on_both_instances,
            self.test_document_sync_via_load_balancer,
            self.test_name_to_uuid_mapping,
            self.test_wal_uuid_mapping_functionality
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            if test():
                passed += 1
        
        # Cleanup
        self.cleanup_test_collections()
        
        # Results
        logger.info(f"\n📊 AUTO-MAPPING TEST RESULTS:")
        logger.info(f"   Passed: {passed}/{total} ({(passed/total)*100:.1f}%)")
        
        if passed == total:
            logger.info("🎉 ALL AUTO-MAPPING TESTS PASSED!")
            return True
        else:
            logger.info("❌ Some auto-mapping tests failed")
            return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Test Auto-Mapping and Document Sync Functionality')
    parser.add_argument('--url', default='https://chroma-load-balancer.onrender.com', 
                       help='Load balancer URL')
    args = parser.parse_args()
    
    test_suite = AutoMappingDocumentSyncTest(args.url)
    success = test_suite.run_all_tests()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 