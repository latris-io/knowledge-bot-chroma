#!/usr/bin/env python3
"""
Comprehensive System Cleanup - Clean PostgreSQL WAL data and ChromaDB test collections
Prepares system for fresh testing after UUID validation fix
"""

import requests
import psycopg2
import os
import time
import logging
from urllib.parse import urlparse

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
            'postgresql://unified_wal_user:wal_secure_2024@dpg-cu5l49bv2p9s73c7l1u0-a.oregon-postgres.render.com/unified_wal_db')
    
    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        try:
            return psycopg2.connect(self.database_url)
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    def cleanup_postgresql_data(self):
        """Clean up all WAL and mapping data from PostgreSQL"""
        logger.info("🧹 Cleaning PostgreSQL WAL and mapping data...")
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Clean up WAL writes table
                    logger.info("  Clearing unified_wal_writes table...")
                    cur.execute("DELETE FROM unified_wal_writes")
                    wal_deleted = cur.rowcount
                    logger.info(f"    ✅ Deleted {wal_deleted} WAL write entries")
                    
                    # Clean up collection mappings
                    logger.info("  Clearing collection_id_mapping table...")
                    cur.execute("DELETE FROM collection_id_mapping")
                    mappings_deleted = cur.rowcount
                    logger.info(f"    ✅ Deleted {mappings_deleted} collection mapping entries")
                    
                    # Clean up any monitoring data if tables exist
                    logger.info("  Clearing monitoring data...")
                    try:
                        cur.execute("DELETE FROM performance_metrics")
                        metrics_deleted = cur.rowcount
                        logger.info(f"    ✅ Deleted {metrics_deleted} performance metric entries")
                    except Exception:
                        logger.info("    ℹ️ Performance metrics table not found (OK)")
                    
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
                        cur.execute("ALTER SEQUENCE IF EXISTS collection_id_mapping_id_seq RESTART WITH 1")
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
        """Clean up test collections from a ChromaDB instance"""
        logger.info(f"🧹 Cleaning {instance_name} ChromaDB collections...")
        
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
            
            # Identify test vs production collections
            for collection in collections:
                name = collection.get('name', '')
                if any(prefix in name for prefix in ['AUTOTEST_', 'test_collection_', 'TEST_', 'temp_']):
                    test_collections.append(collection)
                else:
                    production_collections.append(collection)
            
            logger.info(f"  📊 Found {len(collections)} total collections on {instance_name}:")
            logger.info(f"    🧪 Test collections: {len(test_collections)}")
            logger.info(f"    🏭 Production collections: {len(production_collections)}")
            
            # Delete test collections only
            deleted_count = 0
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
            
            # List production collections that will be preserved
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
                    mapping_count = cur.fetchone()[0]
                    
                    if wal_count == 0 and mapping_count == 0:
                        verification_results['postgresql_clean'] = True
                        logger.info(f"  ✅ PostgreSQL verified clean (WAL: {wal_count}, Mappings: {mapping_count})")
                    else:
                        logger.warning(f"  ⚠️ PostgreSQL not fully clean (WAL: {wal_count}, Mappings: {mapping_count})")
                        
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
                    test_collections = [c for c in collections if any(prefix in c.get('name', '') for prefix in ['AUTOTEST_', 'test_collection_', 'TEST_', 'temp_'])]
                    
                    if len(test_collections) == 0:
                        verification_results[result_key] = True
                        logger.info(f"  ✅ {instance_name} verified clean ({len(collections)} total collections, 0 test collections)")
                    else:
                        logger.warning(f"  ⚠️ {instance_name} still has {len(test_collections)} test collections")
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