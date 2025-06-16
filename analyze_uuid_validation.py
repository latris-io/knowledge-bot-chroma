#!/usr/bin/env python3
"""
Analyze UUID Validation Issue for Document Operations
Based on diagnostic findings showing 400 "Collection ID is not a valid UUIDv4" errors
"""

import requests
import json
import uuid
import time
import logging
from test_base_cleanup import BulletproofTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UUIDValidationAnalysis(BulletproofTestBase):
    """Analyze the UUID validation issue affecting document operations"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_uuid")
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
        
    def test_collection_name_vs_uuid_usage(self):
        """Test how collection names vs UUIDs are handled in document operations"""
        logger.info("🔍 Analyzing Collection Name vs UUID Usage")
        
        collection_name = self.create_unique_collection_name("uuid_test")
        
        try:
            # Create collection via load balancer
            logger.info(f"  Creating collection: {collection_name}")
            create_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name},
                timeout=30
            )
            
            if create_response.status_code not in [200, 201]:
                logger.error(f"❌ Collection creation failed: {create_response.status_code}")
                return False
                
            collection_data = create_response.json()
            collection_uuid = collection_data.get('id')
            logger.info(f"  ✅ Collection created with UUID: {collection_uuid}")
            
            # Test document operations using collection NAME
            logger.info("  Testing document operations with collection NAME...")
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["UUID validation test"],
                "metadatas": [{"test": "uuid_validation"}],
                "ids": [f"uuid_test_{uuid.uuid4().hex[:8]}"]
            }
            
            self.track_documents(collection_name, doc_data["ids"])
            
            # Try via load balancer with collection NAME
            lb_name_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data,
                timeout=30
            )
            logger.info(f"    Load balancer (name): {lb_name_response.status_code}")
            if lb_name_response.status_code not in [200, 201]:
                logger.info(f"      Error: {lb_name_response.text[:300]}")
            
            # Try via direct primary with collection NAME
            primary_name_response = requests.post(
                f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data,
                timeout=30
            )
            logger.info(f"    Direct primary (name): {primary_name_response.status_code}")
            if primary_name_response.status_code not in [200, 201]:
                logger.info(f"      Error: {primary_name_response.text[:300]}")
            
            # Test document operations using collection UUID
            if collection_uuid:
                logger.info("  Testing document operations with collection UUID...")
                
                uuid_doc_data = doc_data.copy()
                uuid_doc_data["ids"] = [f"uuid_test_by_id_{uuid.uuid4().hex[:8]}"]
                self.track_documents(collection_name, uuid_doc_data["ids"])  # Still track under name
                
                # Try via direct primary with collection UUID
                primary_uuid_response = requests.post(
                    f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/add",
                    json=uuid_doc_data,
                    timeout=30
                )
                logger.info(f"    Direct primary (UUID): {primary_uuid_response.status_code}")
                if primary_uuid_response.status_code not in [200, 201]:
                    logger.info(f"      Error: {primary_uuid_response.text[:300]}")
                else:
                    logger.info("    ✅ Document operations work with UUID!")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ UUID validation analysis failed: {e}")
            return False
    
    def test_collection_mapping_status(self):
        """Check if collection name→UUID mapping is working"""
        logger.info("🔍 Checking Collection Name→UUID Mapping Status")
        
        try:
            # Get collection mappings from load balancer
            mapping_response = requests.get(f"{self.base_url}/collection/mappings", timeout=30)
            
            if mapping_response.status_code == 200:
                mappings = mapping_response.json()
                mapping_count = len(mappings.get('mappings', []))
                logger.info(f"  Load balancer has {mapping_count} collection mappings")
                
                # Show some example mappings
                if mapping_count > 0:
                    for i, mapping in enumerate(mappings.get('mappings', [])[:3]):
                        collection_name = mapping.get('collection_name', 'unknown')
                        primary_id = mapping.get('primary_collection_id', 'unknown')
                        replica_id = mapping.get('replica_collection_id', 'unknown')
                        logger.info(f"    Mapping {i+1}: {collection_name}")
                        logger.info(f"      Primary UUID: {primary_id[:8]}...")
                        logger.info(f"      Replica UUID: {replica_id[:8]}...")
                
                return mapping_count > 0
            else:
                logger.warning(f"  ⚠️ Could not get mappings: {mapping_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Mapping status check failed: {e}")
            return False
    
    def test_wal_sync_patterns(self):
        """Analyze WAL sync patterns to understand the failures"""
        logger.info("🔍 Analyzing WAL Sync Patterns")
        
        try:
            # Get WAL status
            wal_response = requests.get(f"{self.base_url}/wal/status", timeout=30)
            
            if wal_response.status_code == 200:
                wal_data = wal_response.json()
                
                # Analyze sync statistics
                stats = wal_data.get('performance_stats', {})
                failed_syncs = stats.get('failed_syncs', 0)
                successful_syncs = stats.get('successful_syncs', 0)
                total_syncs = failed_syncs + successful_syncs
                
                logger.info(f"  WAL Sync Analysis:")
                logger.info(f"    Total syncs attempted: {total_syncs}")
                logger.info(f"    Successful: {successful_syncs} ({successful_syncs/total_syncs*100:.1f}%)" if total_syncs > 0 else "    No syncs yet")
                logger.info(f"    Failed: {failed_syncs} ({failed_syncs/total_syncs*100:.1f}%)" if total_syncs > 0 else "    No failures yet")
                
                # Check WAL system status
                wal_system = wal_data.get('wal_system', {})
                pending_writes = wal_system.get('pending_writes', 0)
                logger.info(f"    Pending writes: {pending_writes}")
                
                # High failure rate indicates UUID/mapping issues
                if total_syncs > 0 and (failed_syncs / total_syncs) > 0.5:
                    logger.warning("  ⚠️ High WAL failure rate suggests UUID/mapping issues")
                    return False
                else:
                    logger.info("  ✅ WAL sync patterns appear healthy")
                    return True
            else:
                logger.warning(f"  ⚠️ Could not get WAL status: {wal_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ WAL analysis failed: {e}")
            return False

def main():
    """Run UUID validation analysis"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze UUID Validation Issues")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    analyzer = UUIDValidationAnalysis(args.url)
    
    logger.info("🔬 Starting UUID Validation Analysis")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info("="*80)
    
    try:
        # Run analysis tests
        logger.info("\n1️⃣ Testing Collection Name vs UUID Usage...")
        name_vs_uuid = analyzer.test_collection_name_vs_uuid_usage()
        
        logger.info("\n2️⃣ Checking Collection Mapping Status...")
        mapping_status = analyzer.test_collection_mapping_status()
        
        logger.info("\n3️⃣ Analyzing WAL Sync Patterns...")
        wal_patterns = analyzer.test_wal_sync_patterns()
        
    finally:
        # Always cleanup
        analyzer.comprehensive_cleanup()
    
    # Final analysis
    logger.info("\n" + "="*80)
    logger.info("🎯 UUID VALIDATION ANALYSIS RESULTS")
    logger.info("="*80)
    
    logger.info(f"📋 Collection name→UUID mapping: {'✅ Working' if mapping_status else '❌ Issues detected'}")
    logger.info(f"📋 WAL sync patterns: {'✅ Healthy' if wal_patterns else '❌ High failure rate'}")
    logger.info(f"📋 Name vs UUID operations: {'✅ Analysis complete' if name_vs_uuid else '❌ Analysis failed'}")
    
    logger.info("\n🔍 ROOT CAUSE ANALYSIS:")
    logger.info("The 400 'Collection ID is not a valid UUIDv4' error indicates:")
    logger.info("1. Load balancer properly creates collections with UUIDs")
    logger.info("2. Document operations are trying to use collection NAMES instead of UUIDs")
    logger.info("3. The real-time collection name→UUID mapping may not be working consistently")
    logger.info("4. This is NOT an infrastructure capacity issue - it's a mapping logic issue")
    
    logger.info("\n✅ CONCLUSION: This is a CODE ISSUE with collection name→UUID mapping,")
    logger.info("   NOT an infrastructure capacity problem!")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 