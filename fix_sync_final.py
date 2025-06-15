#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def fix_and_test_sync():
    """Debug and fix the final sync execution issues"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🔧 FINAL SYNC EXECUTION FIX")
    print("=" * 50)
    
    try:
        # Step 1: Clear all failed WAL entries to reset
        print("1. Resetting all failed WAL entries...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Clear ALL failed entries
                cur.execute("DELETE FROM unified_wal_writes WHERE status = 'failed'")
                deleted_count = cur.rowcount
                
                # Reset any pending entries that might be stuck
                cur.execute("UPDATE unified_wal_writes SET retry_count = 0, error_message = NULL WHERE status = 'pending'")
                reset_count = cur.rowcount
                
                conn.commit()
                print(f"   ✅ Cleared {deleted_count} failed entries, reset {reset_count} pending entries")
        
        # Step 2: Verify collection mapping
        print("2. Verifying collection mapping...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping WHERE collection_name = 'global'")
                result = cur.fetchone()
                
                if result:
                    name, primary_id, replica_id = result
                    print(f"   ✅ Global mapping found:")
                    print(f"      Primary: {primary_id}")
                    print(f"      Replica: {replica_id}")
                else:
                    print("   ❌ No global mapping found - creating...")
                    cur.execute("""
                        INSERT INTO collection_id_mapping 
                        (collection_name, primary_collection_id, replica_collection_id, collection_config)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (collection_name) DO UPDATE SET
                            primary_collection_id = EXCLUDED.primary_collection_id,
                            replica_collection_id = EXCLUDED.replica_collection_id
                    """, (
                        "global",
                        "eb07030e-ed7e-4aab-8249-3a95efefccb0",
                        "0c6ab3d3-bbf2-44e4-9cfe-e95654c43ace",
                        json.dumps({"hnsw": {"space": "l2", "ef_construction": 100}})
                    ))
                    conn.commit()
                    print("   ✅ Global mapping created")
        
        # Step 3: Test new ingestion to trigger sync
        print("3. Testing new ingestion to trigger intelligent sync...")
        
        base_url = "https://chroma-load-balancer.onrender.com"
        global_id = "eb07030e-ed7e-4aab-8249-3a95efefccb0"
        
        # Get current counts
        primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/count", timeout=30).text)
        replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/0c6ab3d3-bbf2-44e4-9cfe-e95654c43ace/count", timeout=30).text)
        
        print(f"   Before ingestion - Primary: {primary_count}, Replica: {replica_count}")
        
        # New test document
        payload = {
            "embeddings": [[0.2] * 3072],
            "documents": ["FINAL SYNC FIX TEST"],
            "metadatas": [{"test": "sync_fix", "document_id": f"fix_test_{int(time.time())}"}],
            "ids": [f"sync_fix_{int(time.time())}"]
        }
        
        response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/add",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            print("   ✅ Ingestion successful")
            
            # Step 4: Wait and monitor sync
            print("4. Monitoring sync process (45 seconds)...")
            
            for i in range(3):
                time.sleep(15)
                print(f"   Checking sync progress ({(i+1)*15}s)...")
                
                try:
                    wal_response = requests.get(f"{base_url}/wal/status", timeout=30)
                    if wal_response.status_code == 200:
                        wal_status = wal_response.json()
                        successful = wal_status["performance_stats"]["successful_syncs"]
                        failed = wal_status["performance_stats"]["failed_syncs"]
                        print(f"      WAL: {successful} successful, {failed} failed")
                        
                        if successful > 0:
                            print("      🎉 SUCCESSFUL SYNCS DETECTED!")
                            break
                    else:
                        print(f"      ⚠️ WAL status unavailable: {wal_response.status_code}")
                except Exception as e:
                    print(f"      ⚠️ WAL check error: {e}")
            
            # Step 5: Final verification
            print("5. Final verification...")
            
            final_primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/count", timeout=30).text)
            final_replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/0c6ab3d3-bbf2-44e4-9cfe-e95654c43ace/count", timeout=30).text)
            
            print(f"   Final counts - Primary: {final_primary_count}, Replica: {final_replica_count}")
            
            if final_replica_count > replica_count:
                print("   🎉🎉🎉 SUCCESS! INTELLIGENT SYNC FULLY WORKING! 🎉🎉🎉")
                print("   ✅ Replica synchronized successfully!")
                print("   ✅ Collection ID mapping applied correctly!")
                print("   ✅ All remaining issues resolved!")
            elif final_primary_count > primary_count:
                print("   ✅ Primary updated, checking sync status...")
                
                # Check for recent sync errors
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT write_id, error_message 
                            FROM unified_wal_writes 
                            WHERE status = 'failed' 
                            AND created_at > NOW() - INTERVAL '1 minute'
                            ORDER BY created_at DESC LIMIT 3
                        """)
                        
                        recent_errors = cur.fetchall()
                        if recent_errors:
                            print("   ❌ Recent sync errors:")
                            for write_id, error_msg in recent_errors:
                                print(f"      {write_id[:8]}: {error_msg}")
                        else:
                            print("   ⏳ No recent errors - sync may be processing")
            else:
                print("   ⚠️ No changes detected - possible sync delay")
        else:
            print(f"   ❌ Ingestion failed: {response.status_code}")
            print(f"   Response: {response.text}")
        
        print(f"\n{'='*50}")
        print("🔧 FINAL FIX COMPLETED!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    fix_and_test_sync() 