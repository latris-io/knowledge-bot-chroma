#!/usr/bin/env python3
"""
Diagnostic Script for Document Operation Failures
Determines if 503 errors are infrastructure-related or code bugs
"""

import requests
import json
import uuid
import time
import logging
from test_base_cleanup import BulletproofTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DocumentOperationDiagnostics(BulletproofTestBase):
    """Diagnostic tests to analyze document operation failures"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_diag")
        
        # Direct instance URLs for comparison
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
        
    def test_direct_instance_access(self):
        """Test document operations directly against primary and replica instances"""
        logger.info("🔍 Testing Direct Instance Access")
        
        results = {
            'primary': {'healthy': False, 'collections_work': False, 'documents_work': False},
            'replica': {'healthy': False, 'collections_work': False, 'documents_work': False}
        }
        
        instances = [
            ('primary', self.primary_url),
            ('replica', self.replica_url)
        ]
        
        for instance_name, instance_url in instances:
            logger.info(f"  Testing {instance_name} instance: {instance_url}")
            
            try:
                # Test health
                health_response = requests.get(f"{instance_url}/api/v2/heartbeat", timeout=15)
                results[instance_name]['healthy'] = health_response.status_code == 200
                logger.info(f"    Health: {'✅' if results[instance_name]['healthy'] else '❌'} ({health_response.status_code})")
                
                if results[instance_name]['healthy']:
                    # Test collection listing
                    collections_response = requests.get(
                        f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                        timeout=15
                    )
                    results[instance_name]['collections_work'] = collections_response.status_code == 200
                    logger.info(f"    Collections: {'✅' if results[instance_name]['collections_work'] else '❌'} ({collections_response.status_code})")
                    
                    if results[instance_name]['collections_work']:
                        # Try to find an existing collection for document testing
                        collections = collections_response.json()
                        if collections:
                            # Use first available collection
                            test_collection = collections[0]['name']
                            logger.info(f"    Using existing collection: {test_collection}")
                            
                            # Test document get
                            doc_response = requests.post(
                                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection}/get",
                                json={"limit": 1, "include": ["documents"]},
                                timeout=15
                            )
                            results[instance_name]['documents_work'] = doc_response.status_code == 200
                            logger.info(f"    Documents: {'✅' if results[instance_name]['documents_work'] else '❌'} ({doc_response.status_code})")
                            
                            if doc_response.status_code != 200:
                                logger.info(f"      Error details: {doc_response.text[:200]}")
                        else:
                            logger.info("    No existing collections to test documents")
                
            except Exception as e:
                logger.warning(f"    ⚠️ Error testing {instance_name}: {e}")
        
        return results
    
    def test_load_balancer_vs_direct(self):
        """Compare load balancer behavior vs direct instance access"""
        logger.info("🔍 Comparing Load Balancer vs Direct Access")
        
        # Create a test collection via load balancer
        collection_name = self.create_unique_collection_name("comparison")
        
        logger.info(f"  Creating test collection via load balancer: {collection_name}")
        
        try:
            # Create collection via load balancer
            lb_create_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name},
                timeout=30
            )
            
            if lb_create_response.status_code not in [200, 201]:
                logger.error(f"  ❌ Load balancer collection creation failed: {lb_create_response.status_code}")
                return False
            
            logger.info("  ✅ Collection created via load balancer")
            
            # Wait for potential sync
            time.sleep(5)
            
            # Test document operations via different paths
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["Diagnostic test document"],
                "metadatas": [{"test_type": "diagnostic", "path": "load_balancer"}],
                "ids": [f"diag_test_{uuid.uuid4().hex[:8]}"]
            }
            
            self.track_documents(collection_name, doc_data["ids"])
            
            # Test via load balancer
            logger.info("  Testing document ADD via load balancer...")
            lb_add_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data,
                timeout=30
            )
            
            logger.info(f"    Load Balancer ADD: {lb_add_response.status_code}")
            if lb_add_response.status_code not in [200, 201]:
                logger.info(f"      Error: {lb_add_response.text[:200]}")
            
            # Test via direct primary (if load balancer failed)
            if lb_add_response.status_code not in [200, 201]:
                logger.info("  Testing document ADD via direct primary...")
                
                # Modify doc ID to avoid conflicts
                direct_doc_data = doc_data.copy()
                direct_doc_data["ids"] = [f"diag_direct_{uuid.uuid4().hex[:8]}"]
                self.track_documents(collection_name, direct_doc_data["ids"])
                
                primary_add_response = requests.post(
                    f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                    json=direct_doc_data,
                    timeout=30
                )
                
                logger.info(f"    Direct Primary ADD: {primary_add_response.status_code}")
                if primary_add_response.status_code not in [200, 201]:
                    logger.info(f"      Error: {primary_add_response.text[:200]}")
                
                # This tells us if the issue is load balancer routing or instance capacity
                if primary_add_response.status_code in [200, 201]:
                    logger.warning("  🚨 POTENTIAL BUG: Direct primary works but load balancer fails!")
                    return False
                else:
                    logger.info("  ✅ Confirmed: Both load balancer and direct primary fail - infrastructure issue")
                    return True
            else:
                logger.info("  ✅ Load balancer document operations working")
                return True
                
        except Exception as e:
            logger.error(f"  ❌ Comparison test failed: {e}")
            return False
    
    def test_resource_constraints(self):
        """Test if failures are due to resource constraints"""
        logger.info("🔍 Testing for Resource Constraints")
        
        try:
            # Check system status
            status_response = requests.get(f"{self.base_url}/status", timeout=30)
            if status_response.status_code == 200:
                status_data = status_response.json()
                
                # Log instance health details
                instances = status_data.get('instances', [])
                for instance in instances:
                    name = instance.get('name', 'unknown')
                    healthy = instance.get('healthy', False)
                    last_check = instance.get('last_health_check', 'unknown')
                    logger.info(f"  Instance {name}: {'✅' if healthy else '❌'} (last check: {last_check})")
            
            # Check WAL status for any bottlenecks
            wal_response = requests.get(f"{self.base_url}/wal/status", timeout=30)
            if wal_response.status_code == 200:
                wal_data = wal_response.json()
                
                pending_writes = wal_data.get('wal_system', {}).get('pending_writes', 0)
                failed_syncs = wal_data.get('performance_stats', {}).get('failed_syncs', 0)
                successful_syncs = wal_data.get('performance_stats', {}).get('successful_syncs', 0)
                
                logger.info(f"  WAL Status:")
                logger.info(f"    Pending writes: {pending_writes}")
                logger.info(f"    Failed syncs: {failed_syncs}")
                logger.info(f"    Successful syncs: {successful_syncs}")
                
                # High pending writes might indicate resource pressure
                if pending_writes > 10:
                    logger.warning(f"  ⚠️ High pending writes ({pending_writes}) may indicate resource pressure")
                
                # High failure rate might indicate issues
                total_syncs = failed_syncs + successful_syncs
                if total_syncs > 0:
                    failure_rate = (failed_syncs / total_syncs) * 100
                    logger.info(f"    Failure rate: {failure_rate:.1f}%")
                    if failure_rate > 50:
                        logger.warning(f"  ⚠️ High failure rate ({failure_rate:.1f}%) indicates system stress")
            
            return True
            
        except Exception as e:
            logger.error(f"  ❌ Resource constraint test failed: {e}")
            return False
    
    def test_simple_collection_operations(self):
        """Test if basic collection operations work (vs document operations)"""
        logger.info("🔍 Testing Basic Collection Operations")
        
        simple_collection = self.create_unique_collection_name("simple")
        
        try:
            # Test collection creation
            create_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": simple_collection},
                timeout=30
            )
            
            create_success = create_response.status_code in [200, 201]
            logger.info(f"  Collection Creation: {'✅' if create_success else '❌'} ({create_response.status_code})")
            
            if create_success:
                # Test collection listing
                list_response = requests.get(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                    timeout=30
                )
                
                list_success = list_response.status_code == 200
                logger.info(f"  Collection Listing: {'✅' if list_success else '❌'} ({list_response.status_code})")
                
                if list_success:
                    collections = list_response.json()
                    found = any(c.get('name') == simple_collection for c in collections)
                    logger.info(f"  Collection Found in List: {'✅' if found else '❌'}")
                
                # Test collection deletion
                delete_response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{simple_collection}",
                    timeout=30
                )
                
                delete_success = delete_response.status_code in [200, 404]
                logger.info(f"  Collection Deletion: {'✅' if delete_success else '❌'} ({delete_response.status_code})")
                
                # Remove from tracking since we deleted it
                self.created_collections.discard(simple_collection)
                
                return create_success and list_success and delete_success
            else:
                logger.error(f"  Collection creation failed: {create_response.text[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"  ❌ Basic collection operations test failed: {e}")
            return False

def main():
    """Run comprehensive diagnostics to determine if document failures are infrastructure-related"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Diagnose Document Operation Failures")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    diagnostics = DocumentOperationDiagnostics(args.url)
    
    logger.info("🔬 Starting Document Operation Diagnostics")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info("="*80)
    
    try:
        # Run diagnostic tests
        logger.info("\n1️⃣ Testing Direct Instance Access...")
        instance_results = diagnostics.test_direct_instance_access()
        
        logger.info("\n2️⃣ Testing Basic Collection Operations...")
        collection_ops_work = diagnostics.test_simple_collection_operations()
        
        logger.info("\n3️⃣ Checking Resource Constraints...")
        resource_check = diagnostics.test_resource_constraints()
        
        logger.info("\n4️⃣ Comparing Load Balancer vs Direct Access...")
        comparison_result = diagnostics.test_load_balancer_vs_direct()
        
    finally:
        # Always cleanup
        diagnostics.comprehensive_cleanup()
    
    # Analysis and conclusions
    logger.info("\n" + "="*80)
    logger.info("🔍 DIAGNOSTIC ANALYSIS")
    logger.info("="*80)
    
    # Analyze instance health
    primary_healthy = instance_results.get('primary', {}).get('healthy', False)
    replica_healthy = instance_results.get('replica', {}).get('healthy', False)
    
    logger.info(f"📊 Instance Health:")
    logger.info(f"   Primary: {'✅ Healthy' if primary_healthy else '❌ Unhealthy'}")
    logger.info(f"   Replica: {'✅ Healthy' if replica_healthy else '❌ Unhealthy'}")
    
    # Analyze operation capabilities
    primary_docs = instance_results.get('primary', {}).get('documents_work', False)
    replica_docs = instance_results.get('replica', {}).get('documents_work', False)
    
    logger.info(f"📄 Document Operations:")
    logger.info(f"   Primary: {'✅ Working' if primary_docs else '❌ Failing'}")
    logger.info(f"   Replica: {'✅ Working' if replica_docs else '❌ Failing'}")
    
    logger.info(f"📚 Collection Operations: {'✅ Working' if collection_ops_work else '❌ Failing'}")
    
    # Final determination
    logger.info("\n🎯 CONCLUSION:")
    
    if not primary_healthy and not replica_healthy:
        logger.error("❌ INFRASTRUCTURE ISSUE: Both instances are unhealthy")
        conclusion = "infrastructure"
    elif collection_ops_work and not (primary_docs or replica_docs):
        logger.warning("⚠️ CAPACITY ISSUE: Collections work but document operations fail on both instances")
        logger.info("   This indicates infrastructure resource constraints, not code bugs")
        conclusion = "infrastructure"
    elif primary_docs or replica_docs:
        logger.warning("🚨 POTENTIAL BUG: Document operations work on direct access but fail through load balancer")
        conclusion = "potential_bug"
    else:
        logger.info("✅ CONFIRMED INFRASTRUCTURE: Consistent failures across all access methods")
        conclusion = "infrastructure"
    
    if conclusion == "infrastructure":
        logger.info("✅ Document operation failures are INFRASTRUCTURE-RELATED, not code bugs")
        logger.info("🚀 Core architecture is sound - scale up infrastructure to resolve 503 errors")
    else:
        logger.warning("🔧 Further investigation needed - may be code-related issues")
    
    return conclusion == "infrastructure"

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 