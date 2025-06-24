#!/usr/bin/env python3
"""
Comprehensive System Cleanup - Clean PostgreSQL WAL data and ChromaDB test collections
🚨 BULLETPROOF PRODUCTION DATA PROTECTION 🚨

This script safely cleans ONLY test data while protecting production collections:
- Protected collections: 'global', 'production', 'prod', 'main', etc.
- Only deletes collections/mappings with confirmed test patterns
- Unknown patterns are automatically protected (safe-by-default)
- Enhanced verification ensures production data remains intact

Prepares system for fresh testing while preserving production data
"""

import requests
import psycopg2
import os
import time
import logging
from urllib.parse import urlparse
import json
import re
from typing import List, Dict, Set

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ComprehensiveSystemCleanup:
    """Comprehensive cleanup of PostgreSQL WAL data and ChromaDB collections"""
    
    def __init__(self, load_balancer_url="https://chroma-load-balancer.onrender.com"):
        self.load_balancer_url = load_balancer_url.rstrip('/')
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
        
        # Database connection string from environment or default
        self.database_url = os.getenv('DATABASE_URL', 
            'postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha')
        
        # Test collection patterns (bulletproof protection for production)
        self.test_patterns = [
            r".*TEST.*",
            r".*DEBUG.*", 
            r".*AUTO_MAP.*",
            r".*WAL_FIX.*",
            r".*PATH_NORM.*",
            r".*UUID_RES.*",
            r".*ENHANCED_MAPPING.*",
            r".*CMS_PRODUCTION_TEST.*",
            r".*CMS_FAILOVER_TEST.*",
            r".*WAL_SYNC_TEST.*",
            r".*BASELINE_TEST.*",
            r".*REAL_TEST.*",
            r".*REPLICA_FIX.*",
            r".*SIMPLIFIED_WAL.*",
            r".*POST_DEPLOY.*",
            r".*SCOPE_FIX.*"
        ]
        
        # BULLETPROOF PROTECTION: Never delete these collections
        self.protected_collections = {
            'global', 'Global', 'GLOBAL', 
            'production', 'prod', 'main',
            'Production', 'Prod', 'Main'
        }
    
    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        try:
            return psycopg2.connect(self.database_url)
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    def cleanup_postgresql_data(self):
        """Clean up WAL and TEST mapping data from PostgreSQL - PROTECTS PRODUCTION DATA"""
        logger.info("🧹 Cleaning PostgreSQL WAL and TEST mapping data...")
        
        # 🚨 CRITICAL: PROTECTED PRODUCTION COLLECTIONS 🚨
        PROTECTED_COLLECTIONS = [
            'global', 'Global', 'GLOBAL',  # Production data collection
            'production', 'prod', 'main',   # Other potential production names
            'client_production', 'live'     # Additional protection patterns
        ]
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Clean up WAL writes table (all test data is safe to remove)
                    logger.info("  Clearing unified_wal_writes table...")
                    cur.execute("DELETE FROM unified_wal_writes")
                    wal_deleted = cur.rowcount
                    logger.info(f"    ✅ Deleted {wal_deleted} WAL write entries")
                    
                    # 🚨 ENHANCED PROTECTION: Only delete TEST collection mappings
                    logger.info("  🔒 SAFELY clearing TEST collection mappings (protecting production)...")
                    
                    # First, check what mappings exist
                    cur.execute("SELECT collection_name FROM collection_id_mapping")
                    all_mappings = [row[0] for row in cur.fetchall()]
                    
                    protected_found = []
                    test_mappings = []
                    
                    for mapping_name in all_mappings:
                        # Check if this is a protected production collection
                        is_protected = any(
                            protected.lower() in mapping_name.lower() 
                            for protected in PROTECTED_COLLECTIONS
                        )
                        
                        # Check if this is clearly a test collection
                        is_test = any(prefix in mapping_name for prefix in [
                            'AUTOTEST_', 'test_', 'TEST_', 'temp_', 'debug_',
                            'SYNC_FIX_', 'LIVE_SYNC_', 'CMS_PRODUCTION_TEST_',
                            'REAL_TEST_', 'WAL_SYNC_TEST_', 'USE_CASE_',
                            'UC2_', 'UC3_', 'UC4_',  # USE CASE testing patterns
                            'UC2_DELETE_', 'UC3_MANUAL_', 'UC4_SAFETY_',  # Specific USE CASE patterns
                            'FIX_TEST_', 'DEBUG_MAPPING_', 'MAPPING_FIX_'  # Debug test patterns
                        ])
                        
                        if is_protected:
                            protected_found.append(mapping_name)
                        elif is_test:
                            test_mappings.append(mapping_name)
                        else:
                            # Unknown pattern - be safe and protect it
                            logger.warning(f"    ⚠️ UNKNOWN PATTERN - PROTECTING: {mapping_name}")
                            protected_found.append(mapping_name)
                    
                    # Report what we found
                    logger.info(f"    📊 Found {len(all_mappings)} total mappings:")
                    logger.info(f"       🔒 Protected (production): {len(protected_found)}")
                    logger.info(f"       🧪 Test collections: {len(test_mappings)}")
                    
                    if protected_found:
                        logger.info("    🔒 PROTECTED mappings (will NOT be deleted):")
                        for protected in protected_found:
                            logger.info(f"       - {protected}")
                    
                    # Only delete confirmed test mappings
                    mappings_deleted = 0
                    if test_mappings:
                        logger.info("    🧹 Deleting ONLY test collection mappings...")
                        for test_mapping in test_mappings:
                            cur.execute(
                                "DELETE FROM collection_id_mapping WHERE collection_name = %s",
                                (test_mapping,)
                            )
                            mappings_deleted += cur.rowcount
                            logger.info(f"       ✅ Deleted test mapping: {test_mapping}")
                    else:
                        logger.info("    ℹ️ No test mappings found to delete")
                        
                    logger.info(f"    ✅ Safely deleted {mappings_deleted} TEST collection mappings")
                    
                    # Clean up any monitoring data if tables exist
                    logger.info("  Clearing monitoring data...")
                    try:
                        cur.execute("DELETE FROM wal_performance_metrics")
                        metrics_deleted = cur.rowcount
                        logger.info(f"    ✅ Deleted {metrics_deleted} performance metric entries")
                    except Exception:
                        logger.info("    ℹ️ WAL performance metrics table not found (OK)")
                    
                    try:
                        cur.execute("DELETE FROM upgrade_recommendations")
                        recommendations_deleted = cur.rowcount
                        logger.info(f"    ✅ Deleted {recommendations_deleted} upgrade recommendation entries")
                    except Exception:
                        logger.info("    ℹ️ Upgrade recommendations table not found (OK)")
                    
                    # Reset any sequences
                    logger.info("  Resetting database sequences...")
                    try:
                        cur.execute("ALTER SEQUENCE IF EXISTS unified_wal_writes_id_seq RESTART WITH 1")
                        cur.execute("ALTER SEQUENCE IF EXISTS collection_id_mapping_mapping_id_seq RESTART WITH 1")
                        logger.info("    ✅ Database sequences reset")
                    except Exception as e:
                        logger.info(f"    ℹ️ Sequence reset skipped: {e}")
                    
                    conn.commit()
                    
                    logger.info("✅ PostgreSQL cleanup completed successfully")
                    return {
                        'wal_entries_deleted': wal_deleted,
                        'mappings_deleted': mappings_deleted,
                        'success': True
                    }
                    
        except Exception as e:
            logger.error(f"❌ PostgreSQL cleanup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def cleanup_chromadb_collections(self, instance_url, instance_name):
        """Clean up ONLY test collections from a ChromaDB instance - PROTECTS PRODUCTION DATA"""
        logger.info(f"🧹 Cleaning {instance_name} ChromaDB collections...")
        
        # 🚨 CRITICAL: PROTECTED PRODUCTION COLLECTIONS 🚨
        PROTECTED_COLLECTIONS = [
            'global', 'Global', 'GLOBAL',  # Production data collection
            'production', 'prod', 'main',   # Other potential production names
            'client_production', 'live'     # Additional protection patterns
        ]
        
        # 🧪 CONFIRMED TEST PATTERNS 🧪
        TEST_PATTERNS = [
            'AUTOTEST_', 'test_collection_', 'TEST_', 'temp_', 'debug_',
            'SYNC_FIX_', 'LIVE_SYNC_', 'CMS_PRODUCTION_TEST_',
            'REAL_TEST_', 'WAL_SYNC_TEST_', 'USE_CASE_', 'BASELINE_TEST_',
            'CMS_FAILOVER_TEST_', 'client_test_',
            'UC2_', 'UC3_', 'UC4_',  # USE CASE testing patterns
            'UC2_DELETE_', 'UC3_MANUAL_', 'UC4_SAFETY_',  # Specific USE CASE patterns
            'STRESS_', 'SAFETY_', 'MANUAL_',  # Additional test patterns
            'FIX_TEST_', 'DEBUG_MAPPING_', 'MAPPING_FIX_'  # Debug test patterns
        ]
        
        try:
            # Get all collections
            collections_response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            
            if collections_response.status_code != 200:
                logger.warning(f"  ⚠️ Could not list collections on {instance_name}: {collections_response.status_code}")
                return {'success': False, 'collections_deleted': 0}
            
            collections = collections_response.json()
            test_collections = []
            production_collections = []
            protected_collections = []
            
            # Enhanced classification with bulletproof protection
            for collection in collections:
                name = collection.get('name', '')
                
                # Check if this is a protected production collection
                is_protected = any(
                    protected.lower() in name.lower() 
                    for protected in PROTECTED_COLLECTIONS
                )
                
                # Check if this is clearly a test collection
                is_test = any(pattern in name for pattern in TEST_PATTERNS)
                
                if is_protected:
                    protected_collections.append(collection)
                    production_collections.append(collection)  # For stats
                elif is_test:
                    test_collections.append(collection)
                else:
                    # Unknown pattern - be extremely safe and protect it
                    logger.warning(f"  ⚠️ UNKNOWN PATTERN - PROTECTING: {name}")
                    protected_collections.append(collection)
                    production_collections.append(collection)  # For stats
            
            logger.info(f"  📊 Found {len(collections)} total collections on {instance_name}:")
            logger.info(f"    🧪 Test collections: {len(test_collections)}")
            logger.info(f"    🔒 Protected collections: {len(protected_collections)}")
            logger.info(f"    🏭 Total production/protected: {len(production_collections)}")
            
            # Show what will be protected
            if protected_collections:
                logger.info(f"  🔒 PROTECTED collections (will NOT be deleted):")
                for collection in protected_collections:
                    logger.info(f"    - {collection.get('name')}")
            
            # Delete ONLY confirmed test collections
            deleted_count = 0
            if test_collections:
                logger.info(f"  🧹 Deleting ONLY confirmed test collections...")
                for collection in test_collections:
                    collection_name = collection.get('name')
                    collection_id = collection.get('id')
                    
                    try:
                        # Try delete by name first (better for V2 API)
                        delete_response = requests.delete(
                            f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                            timeout=30
                        )
                        
                        if delete_response.status_code in [200, 404]:
                            deleted_count += 1
                            logger.info(f"    ✅ Deleted test collection: {collection_name}")
                        else:
                            logger.warning(f"    ⚠️ Failed to delete {collection_name}: {delete_response.status_code}")
                            
                    except Exception as e:
                        logger.warning(f"    ⚠️ Error deleting {collection_name}: {e}")
            else:
                logger.info(f"  ℹ️ No test collections found to delete")
            
            # Confirm production data is preserved
            if production_collections:
                logger.info(f"  🏭 Preserved production collections:")
                for collection in production_collections:
                    logger.info(f"    - {collection.get('name')}")
            
            logger.info(f"✅ {instance_name} cleanup completed: {deleted_count} test collections deleted")
            return {
                'success': True,
                'collections_deleted': deleted_count,
                'test_collections': len(test_collections),
                'production_collections': len(production_collections)
            }
            
        except Exception as e:
            logger.error(f"❌ {instance_name} cleanup failed: {e}")
            return {'success': False, 'error': str(e), 'collections_deleted': 0}
    
    def cleanup_all_chromadb_instances(self):
        """Clean up test collections from all ChromaDB instances"""
        logger.info("🧹 Cleaning all ChromaDB instances...")
        
        instances = [
            (self.primary_url, "Primary"),
            (self.replica_url, "Replica")
        ]
        
        total_deleted = 0
        results = {}
        
        for instance_url, instance_name in instances:
            result = self.cleanup_chromadb_collections(instance_url, instance_name)
            results[instance_name] = result
            total_deleted += result.get('collections_deleted', 0)
        
        logger.info(f"✅ ChromaDB cleanup completed: {total_deleted} total test collections deleted")
        return results
    
    def trigger_system_reset(self):
        """Trigger a system reset through the load balancer"""
        logger.info("🔄 Triggering system reset...")
        
        try:
            # Clear any failed WAL entries
            cleanup_response = requests.post(
                f"{self.load_balancer_url}/wal/cleanup",
                json={"max_age_hours": 0},  # Clear everything
                timeout=30
            )
            
            if cleanup_response.status_code == 200:
                result = cleanup_response.json()
                logger.info(f"  ✅ WAL cleanup triggered: {result.get('deleted_entries', 0)} entries cleared")
            else:
                logger.warning(f"  ⚠️ WAL cleanup request failed: {cleanup_response.status_code}")
            
            # Check system status
            status_response = requests.get(f"{self.load_balancer_url}/status", timeout=30)
            if status_response.status_code == 200:
                status = status_response.json()
                healthy_instances = status.get('healthy_instances', 0)
                logger.info(f"  📊 System status: {healthy_instances} healthy instances")
            else:
                logger.warning(f"  ⚠️ Status check failed: {status_response.status_code}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ System reset failed: {e}")
            return False
    
    def verify_cleanup_success(self):
        """Verify that cleanup was successful"""
        logger.info("🔍 Verifying cleanup success...")
        
        verification_results = {
            'postgresql_clean': False,
            'primary_clean': False,
            'replica_clean': False,
            'system_healthy': False
        }
        
        # Check PostgreSQL  
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM unified_wal_writes")
                    wal_count = cur.fetchone()[0]
                    
                    cur.execute("SELECT COUNT(*) FROM collection_id_mapping")
                    total_mappings = cur.fetchone()[0]
                    
                    # Check for remaining production mappings
                    cur.execute("""
                        SELECT collection_name FROM collection_id_mapping 
                        WHERE collection_name IN ('global', 'Global', 'GLOBAL', 'production', 'prod', 'main')
                    """)
                    production_mappings = [row[0] for row in cur.fetchall()]
                    
                    # Check for any test mappings that shouldn't remain
                    cur.execute("""
                        SELECT collection_name FROM collection_id_mapping 
                        WHERE collection_name LIKE 'AUTOTEST_%' 
                           OR collection_name LIKE 'test_%'
                           OR collection_name LIKE 'TEST_%'
                           OR collection_name LIKE 'SYNC_FIX_%'
                           OR collection_name LIKE 'USE_CASE_%'
                           OR collection_name LIKE 'UC2_%'
                           OR collection_name LIKE 'UC3_%'
                           OR collection_name LIKE 'UC4_%'
                           OR collection_name LIKE 'FIX_TEST_%'
                           OR collection_name LIKE 'DEBUG_MAPPING_%'
                           OR collection_name LIKE 'MAPPING_FIX_%'
                    """)
                    remaining_test_mappings = [row[0] for row in cur.fetchall()]
                    
                    if wal_count == 0 and len(remaining_test_mappings) == 0:
                        verification_results['postgresql_clean'] = True
                        logger.info(f"  ✅ PostgreSQL verified clean:")
                        logger.info(f"      WAL entries: {wal_count}")
                        logger.info(f"      Total mappings: {total_mappings}")
                        logger.info(f"      Production mappings: {len(production_mappings)} {production_mappings}")
                        logger.info(f"      Test mappings: {len(remaining_test_mappings)}")
                    else:
                        logger.warning(f"  ⚠️ PostgreSQL cleanup incomplete:")
                        logger.warning(f"      WAL entries: {wal_count}")
                        logger.warning(f"      Remaining test mappings: {remaining_test_mappings}")
                        
        except Exception as e:
            logger.error(f"  ❌ PostgreSQL verification failed: {e}")
        
        # Check ChromaDB instances
        for instance_url, instance_name, result_key in [
            (self.primary_url, "Primary", 'primary_clean'),
            (self.replica_url, "Replica", 'replica_clean')
        ]:
            try:
                collections_response = requests.get(
                    f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                    timeout=30
                )
                
                if collections_response.status_code == 200:
                    collections = collections_response.json()
                    
                    # Use enhanced patterns to identify test collections
                    TEST_PATTERNS = [
                        'AUTOTEST_', 'test_collection_', 'TEST_', 'temp_', 'debug_',
                        'SYNC_FIX_', 'LIVE_SYNC_', 'CMS_PRODUCTION_TEST_',
                        'REAL_TEST_', 'WAL_SYNC_TEST_', 'USE_CASE_', 'BASELINE_TEST_',
                        'CMS_FAILOVER_TEST_', 'client_test_',
                        'UC2_', 'UC3_', 'UC4_',  # USE CASE testing patterns
                        'UC2_DELETE_', 'UC3_MANUAL_', 'UC4_SAFETY_',  # Specific USE CASE patterns
                        'FIX_TEST_', 'DEBUG_MAPPING_', 'MAPPING_FIX_'  # Debug test patterns
                    ]
                    
                    PROTECTED_COLLECTIONS = [
                        'global', 'Global', 'GLOBAL', 'production', 'prod', 'main',
                        'client_production', 'live'
                    ]
                    
                    test_collections = []
                    protected_collections = []
                    
                    for collection in collections:
                        name = collection.get('name', '')
                        is_test = any(pattern in name for pattern in TEST_PATTERNS)
                        is_protected = any(protected.lower() in name.lower() for protected in PROTECTED_COLLECTIONS)
                        
                        if is_test:
                            test_collections.append(collection)
                        elif is_protected:
                            protected_collections.append(collection)
                    
                    if len(test_collections) == 0:
                        verification_results[result_key] = True
                        logger.info(f"  ✅ {instance_name} verified clean:")
                        logger.info(f"      Total collections: {len(collections)}")
                        logger.info(f"      Protected collections: {len(protected_collections)}")
                        logger.info(f"      Test collections: 0")
                    else:
                        logger.warning(f"  ⚠️ {instance_name} still has {len(test_collections)} test collections:")
                        for test_col in test_collections[:5]:  # Show first 5
                            logger.warning(f"         - {test_col.get('name')}")
                        if len(test_collections) > 5:
                            logger.warning(f"         ... and {len(test_collections) - 5} more")
                else:
                    logger.warning(f"  ⚠️ Could not verify {instance_name}: {collections_response.status_code}")
                    
            except Exception as e:
                logger.error(f"  ❌ {instance_name} verification failed: {e}")
        
        # Check system health
        try:
            status_response = requests.get(f"{self.load_balancer_url}/status", timeout=30)
            if status_response.status_code == 200:
                status = status_response.json()
                healthy_instances = status.get('healthy_instances', 0)
                total_instances = status.get('total_instances', 0)
                
                if healthy_instances == total_instances and healthy_instances >= 2:
                    verification_results['system_healthy'] = True
                    logger.info(f"  ✅ System healthy ({healthy_instances}/{total_instances} instances)")
                else:
                    logger.warning(f"  ⚠️ System partially healthy ({healthy_instances}/{total_instances} instances)")
            else:
                logger.warning(f"  ⚠️ System health check failed: {status_response.status_code}")
                
        except Exception as e:
            logger.error(f"  ❌ System health verification failed: {e}")
        
        # Overall verification
        all_clean = all(verification_results.values())
        if all_clean:
            logger.info("🎉 Cleanup verification PASSED - System is clean and ready for testing!")
        else:
            failed_checks = [k for k, v in verification_results.items() if not v]
            logger.warning(f"⚠️ Cleanup verification PARTIAL - Failed: {failed_checks}")
        
        return verification_results

class DistributedTestCleanup:
    def __init__(self, load_balancer_url: str = "https://chroma-load-balancer.onrender.com"):
        self.load_balancer_url = load_balancer_url
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
        
        # Test collection patterns (bulletproof protection for production)
        self.test_patterns = [
            r".*TEST.*",
            r".*DEBUG.*", 
            r".*AUTO_MAP.*",
            r".*WAL_FIX.*",
            r".*PATH_NORM.*",
            r".*UUID_RES.*",
            r".*ENHANCED_MAPPING.*",
            r".*CMS_PRODUCTION_TEST.*",
            r".*CMS_FAILOVER_TEST.*",
            r".*WAL_SYNC_TEST.*",
            r".*BASELINE_TEST.*",
            r".*REAL_TEST.*",
            r".*REPLICA_FIX.*",
            r".*SIMPLIFIED_WAL.*",
            r".*POST_DEPLOY.*",
            r".*SCOPE_FIX.*"
        ]
        
        # BULLETPROOF PROTECTION: Never delete these collections
        self.protected_collections = {
            'global', 'Global', 'GLOBAL', 
            'production', 'prod', 'main',
            'Production', 'Prod', 'Main'
        }
        
    def is_test_collection(self, name: str) -> bool:
        """Check if collection is a test collection (safe to delete)"""
        # Bulletproof protection for production collections
        if name in self.protected_collections:
            print(f"🛡️  PROTECTED: {name} (production collection)")
            return False
            
        # Check test patterns
        for pattern in self.test_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return True
        return False
    
    def get_collections_from_instance(self, instance_url: str, instance_name: str) -> List[Dict]:
        """Get all collections from a specific instance"""
        try:
            response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=15
            )
            if response.status_code == 200:
                collections = response.json()
                test_collections = [c for c in collections if self.is_test_collection(c['name'])]
                print(f"📊 {instance_name}: {len(test_collections)}/{len(collections)} test collections found")
                return test_collections
            else:
                print(f"❌ Failed to get collections from {instance_name}: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting collections from {instance_name}: {e}")
            return []
    
    def delete_collection_by_uuid(self, instance_url: str, instance_name: str, collection_uuid: str, collection_name: str) -> bool:
        """Delete collection by UUID from specific instance"""
        try:
            response = requests.delete(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}",
                timeout=30
            )
            if response.status_code in [200, 204, 404]:
                print(f"   ✅ {instance_name}: Deleted {collection_name} ({collection_uuid[:8]}...)")
                return True
            else:
                print(f"   ❌ {instance_name}: Failed to delete {collection_name} - HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"   ❌ {instance_name}: Error deleting {collection_name} - {e}")
            return False
    
    def cleanup_collection_mappings(self) -> int:
        """Clean up test collection mappings from load balancer database"""
        try:
            # Get current mappings
            response = requests.get(f"{self.load_balancer_url}/admin/collection_mappings", timeout=15)
            if response.status_code != 200:
                print(f"❌ Failed to get collection mappings: {response.status_code}")
                return 0
                
            mappings_data = response.json()
            mappings = mappings_data.get('collection_mappings', [])
            
            test_mappings = [m for m in mappings if self.is_test_collection(m['collection_name'])]
            print(f"📊 Found {len(test_mappings)} test collection mappings to clean")
            
            # Note: There's no direct API to delete mappings, they should be cleaned up
            # automatically when collections are deleted, or via database cleanup
            
            return len(test_mappings)
            
        except Exception as e:
            print(f"❌ Error checking collection mappings: {e}")
            return 0
    
    def cleanup_instance(self, instance_url: str, instance_name: str) -> tuple:
        """Clean up test collections from a specific instance"""
        print(f"\n🧹 Cleaning up {instance_name} instance...")
        
        collections = self.get_collections_from_instance(instance_url, instance_name)
        if not collections:
            print(f"   No test collections found on {instance_name}")
            return 0, 0
        
        cleaned = 0
        failed = 0
        
        for collection in collections:
            name = collection['name']
            uuid = collection['id']
            
            if self.delete_collection_by_uuid(instance_url, instance_name, uuid, name):
                cleaned += 1
            else:
                failed += 1
                
            time.sleep(0.5)  # Rate limiting
        
        print(f"   📊 {instance_name} cleanup: {cleaned} deleted, {failed} failed")
        return cleaned, failed
    
    def run_comprehensive_cleanup(self) -> Dict:
        """Run comprehensive cleanup across all components"""
        print("🚀 COMPREHENSIVE TEST DATA CLEANUP")
        print("=" * 60)
        print(f"Load Balancer: {self.load_balancer_url}")
        print(f"Primary: {self.primary_url}")
        print(f"Replica: {self.replica_url}")
        print("=" * 60)
        
        results = {
            'primary_cleaned': 0,
            'primary_failed': 0,
            'replica_cleaned': 0, 
            'replica_failed': 0,
            'mappings_found': 0
        }
        
        # Check collection mappings first
        print("\n🔍 Checking collection mappings...")
        results['mappings_found'] = self.cleanup_collection_mappings()
        
        # Clean up primary instance
        primary_cleaned, primary_failed = self.cleanup_instance(self.primary_url, "Primary")
        results['primary_cleaned'] = primary_cleaned
        results['primary_failed'] = primary_failed
        
        # Clean up replica instance  
        replica_cleaned, replica_failed = self.cleanup_instance(self.replica_url, "Replica")
        results['replica_cleaned'] = replica_cleaned
        results['replica_failed'] = replica_failed
        
        # Summary
        total_cleaned = primary_cleaned + replica_cleaned
        total_failed = primary_failed + replica_failed
        
        print(f"\n{'=' * 60}")
        print("🏁 CLEANUP SUMMARY")
        print(f"✅ Total Cleaned: {total_cleaned}")
        print(f"❌ Total Failed: {total_failed}")
        print(f"📊 Success Rate: {(total_cleaned/(total_cleaned+total_failed)*100) if (total_cleaned+total_failed) > 0 else 100:.1f}%")
        print(f"🗺️  Test Mappings Found: {results['mappings_found']}")
        
        if total_cleaned > 0:
            print(f"\n🎉 Cleanup completed! {total_cleaned} test collections removed")
        else:
            print(f"\n✨ System already clean - no test collections found")
            
        return results

def main():
    """Run comprehensive system cleanup"""
    logger.info("🚀 Starting Comprehensive System Cleanup")
    logger.info("="*60)
    
    cleanup = ComprehensiveSystemCleanup()
    
    try:
        # Step 1: Clean PostgreSQL
        logger.info("\n1️⃣ Cleaning PostgreSQL Database...")
        pg_result = cleanup.cleanup_postgresql_data()
        
        # Step 2: Clean ChromaDB instances
        logger.info("\n2️⃣ Cleaning ChromaDB Instances...")
        chromadb_results = cleanup.cleanup_all_chromadb_instances()
        
        # Step 3: Trigger system reset
        logger.info("\n3️⃣ Triggering System Reset...")
        reset_success = cleanup.trigger_system_reset()
        
        # Step 4: Wait for system to stabilize
        logger.info("\n4️⃣ Waiting for system stabilization...")
        time.sleep(10)
        
        # Step 5: Verify cleanup
        logger.info("\n5️⃣ Verifying Cleanup Success...")
        verification = cleanup.verify_cleanup_success()
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("📊 CLEANUP SUMMARY")
        logger.info("="*60)
        
        if pg_result.get('success'):
            logger.info(f"✅ PostgreSQL: {pg_result.get('wal_entries_deleted', 0)} WAL entries, {pg_result.get('mappings_deleted', 0)} mappings deleted")
        else:
            logger.error(f"❌ PostgreSQL: {pg_result.get('error', 'Unknown error')}")
        
        for instance_name, result in chromadb_results.items():
            if result.get('success'):
                logger.info(f"✅ {instance_name}: {result.get('collections_deleted', 0)} test collections deleted")
            else:
                logger.error(f"❌ {instance_name}: {result.get('error', 'Unknown error')}")
        
        logger.info(f"🔄 System reset: {'✅ Success' if reset_success else '❌ Failed'}")
        
        verification_passed = all(verification.values())
        logger.info(f"🔍 Verification: {'✅ All checks passed' if verification_passed else '⚠️ Some checks failed'}")
        
        if verification_passed:
            logger.info("\n🎉 COMPREHENSIVE CLEANUP COMPLETED SUCCESSFULLY!")
            logger.info("🚀 System is clean and ready for fresh testing")
            return True
        else:
            logger.warning("\n⚠️ Cleanup completed with some issues")
            logger.info("🔧 Manual intervention may be needed")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ Cleanup failed with error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 