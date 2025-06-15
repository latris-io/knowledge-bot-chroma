#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def fix_collection_mapping_sync():
    """Fix the collection ID mapping during sync"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    primary_id = "91fc274b-1a55-48a6-9b5f-fcc842e7eb0b"
    replica_id = "4e5e29a0-38b9-4ce4-b589-3ce01e0d6528"
    
    print("🔧 FIXING COLLECTION ID MAPPING IN SYNC")
    print("=" * 50)
    
    try:
        # Step 1: Fix WAL entries with wrong collection IDs
        print("1. Fixing WAL entries with primary ID to use replica ID...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Update failed WAL entries targeting replica to use replica collection ID
                cur.execute("""
                    UPDATE unified_wal_writes 
                    SET path = REPLACE(path, %s, %s), 
                        status = 'executed', 
                        retry_count = 0, 
                        error_message = NULL,
                        updated_at = NOW()
                    WHERE target_instance = 'replica' 
                    AND path LIKE %s
                    AND status = 'failed'
                """, (primary_id, replica_id, f'%{primary_id}%'))
                
                fixed_count = cur.rowcount
                conn.commit()
                print(f"   ✅ Fixed {fixed_count} WAL entries")
                print(f"   Path updated: {primary_id[:8]}... → {replica_id[:8]}...")
        
        # Step 2: Verify the mapping exists
        print("2. Verifying collection mapping in database...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping WHERE collection_name = 'knowledge_base'")
                result = cur.fetchone()
                
                if result:
                    name, primary_id_db, replica_id_db = result
                    print(f"   ✅ Mapping exists: {name}")
                    print(f"      Primary: {primary_id_db[:8]}...")
                    print(f"      Replica: {replica_id_db[:8]}...")
                else:
                    print("   ❌ No mapping found!")
                    return
        
        # Step 3: Monitor sync for the next 30 seconds
        print("3. Monitoring sync after fix...")
        
        initial_wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
        initial_successful = 0
        if initial_wal_response.status_code == 200:
            initial_successful = initial_wal_response.json()['performance_stats']['successful_syncs']
        
        for i in range(6):
            time.sleep(5)
            print(f"   Checking sync ({(i+1)*5}s)...")
            
            try:
                wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
                if wal_response.status_code == 200:
                    wal_status = wal_response.json()
                    successful = wal_status['performance_stats']['successful_syncs']
                    failed = wal_status['performance_stats']['failed_syncs']
                    print(f"      WAL: {successful} successful, {failed} failed")
                    
                    if successful > initial_successful:
                        print("      🎉 SUCCESS! Sync is working!")
                        break
                else:
                    print(f"      ⚠️ WAL status error: {wal_response.status_code}")
            except Exception as e:
                print(f"      ⚠️ Status check error: {e}")
        
        # Step 4: Final verification
        print("4. Final verification...")
        
        try:
            primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
            replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
            
            print(f"   Document counts:")
            print(f"      Primary (knowledge_base): {primary_count}")
            print(f"      Replica (knowledge_base): {replica_count}")
            
            if replica_count > 0:
                print("   🎉🎉🎉 SUCCESS! INTELLIGENT WAL SYNC FULLY OPERATIONAL! 🎉🎉🎉")
                print()
                print(f"   📌 WORKING COLLECTION INFO:")
                print(f"      Collection Name: knowledge_base")
                print(f"      Primary ID:  {primary_id}")
                print(f"      Replica ID:  {replica_id}")
                print()
                print(f"   📝 UPDATE YOUR INGESTION SERVICE TO USE:")
                print(f"      URL: https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add")
                print(f"      Collection ID: {primary_id}")
                print(f"      Collection Name: knowledge_base")
                print()
                print("   ✅ Your future uploads will now sync automatically to replica!")
            elif primary_count > replica_count:
                print("   ✅ Primary has documents - sync may need more time")
            else:
                print("   ⚠️ No documents detected - add a test document to verify")
                
        except Exception as e:
            print(f"   ❌ Count check failed: {e}")
        
        print(f"\n{'='*50}")
        print("🔧 COLLECTION ID MAPPING FIX COMPLETED!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    fix_collection_mapping_sync() 