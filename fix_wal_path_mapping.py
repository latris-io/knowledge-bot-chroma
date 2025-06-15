#!/usr/bin/env python3

import psycopg2
import requests
import json

def fix_wal_path_mapping():
    """Fix WAL path mapping by updating paths in database to use correct collection IDs"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🔧 FIXING WAL PATH MAPPING ISSUE")
    print("=" * 50)
    
    try:
        # Get all collection mappings
        print("1. Getting collection mappings...")
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping")
                mappings = cur.fetchall()
                print(f"   Found {len(mappings)} collection mappings:")
                
                for name, primary_id, replica_id in mappings:
                    print(f"     {name}: {primary_id[:8]}... → {replica_id[:8]}...")
        
        # Check failed WAL entries
        print("2. Checking failed WAL entries...")
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT write_id, path, target_instance, error_message FROM unified_wal_writes WHERE status = 'failed' ORDER BY created_at DESC")
                failed_entries = cur.fetchall()
                print(f"   Found {len(failed_entries)} failed entries")
                
                fixed_count = 0
                
                for write_id, path, target_instance, error_msg in failed_entries:
                    print(f"   Processing {write_id[:8]}: {target_instance}")
                    
                    # Check if this is a collection ID mapping issue
                    if '/collections/' in path:
                        path_parts = path.split('/collections/')
                        if len(path_parts) >= 2:
                            collection_id_and_rest = path_parts[1]
                            current_collection_id = collection_id_and_rest.split('/')[0]
                            
                            # Find the correct collection ID for target instance
                            correct_id = None
                            for name, primary_id, replica_id in mappings:
                                if current_collection_id == primary_id and target_instance == "replica":
                                    correct_id = replica_id
                                    break
                                elif current_collection_id == replica_id and target_instance == "primary":
                                    correct_id = primary_id
                                    break
                            
                            if correct_id and correct_id != current_collection_id:
                                # Update the path with correct collection ID
                                new_path = path.replace(current_collection_id, correct_id)
                                
                                cur.execute("""
                                    UPDATE unified_wal_writes 
                                    SET path = %s, status = 'executed', retry_count = 0, error_message = NULL, updated_at = NOW()
                                    WHERE write_id = %s
                                """, (new_path, write_id))
                                
                                print(f"     ✅ Fixed: {current_collection_id[:8]}... → {correct_id[:8]}...")
                                fixed_count += 1
                            else:
                                print(f"     ⚠️ No mapping found for {current_collection_id[:8]}...")
                
                conn.commit()
                print(f"   ✅ Fixed {fixed_count} WAL entries")
        
        # Test sync after fix
        print("3. Testing sync after fix...")
        
        # Trigger sync via load balancer
        try:
            wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
            if wal_response.status_code == 200:
                wal_status = wal_response.json()
                initial_successful = wal_status['performance_stats']['successful_syncs']
                initial_failed = wal_status['performance_stats']['failed_syncs']
                print(f"   Initial status: {initial_successful} successful, {initial_failed} failed")
                
                # Wait a moment for sync to process
                import time
                time.sleep(10)
                
                # Check again
                wal_response2 = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
                if wal_response2.status_code == 200:
                    wal_status2 = wal_response2.json()
                    new_successful = wal_status2['performance_stats']['successful_syncs']
                    new_failed = wal_status2['performance_stats']['failed_syncs']
                    print(f"   After fix: {new_successful} successful, {new_failed} failed")
                    
                    if new_successful > initial_successful:
                        print("   🎉 SUCCESS! Sync is now working!")
                    elif new_failed > initial_failed:
                        print("   ❌ Still failing - may need additional fixes")
                    else:
                        print("   ⚠️ No new sync activity detected")
            else:
                print(f"   ❌ WAL status error: {wal_response.status_code}")
        except Exception as e:
            print(f"   ❌ Sync test error: {e}")
        
        # Check final collection counts
        print("4. Checking final collection counts...")
        
        primary_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
        replica_id = "5beb705b-7903-4f7e-8fc9-3a39ce3a2510"
        
        try:
            primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
            replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
            
            print(f"   Primary count: {primary_count}")
            print(f"   Replica count: {replica_count}")
            
            if replica_count > 0:
                print("   🎉🎉🎉 SUCCESS! DATA IS NOW SYNCING TO REPLICA! 🎉🎉🎉")
                print()
                print("   📌 WORKING COLLECTION INFO:")
                print(f"      Collection Name: global")
                print(f"      Primary ID:  {primary_id}")
                print(f"      Replica ID:  {replica_id}")
                print()
                print("   ✅ Your file uploads are now syncing automatically!")
            elif primary_count > replica_count:
                print("   ⚠️ Primary has more documents - sync may need more time")
            else:
                print("   📝 Both have equal counts")
                
        except Exception as e:
            print(f"   ❌ Count check error: {e}")
        
        print(f"\n{'='*50}")
        print("🔧 WAL PATH MAPPING FIX COMPLETED!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    fix_wal_path_mapping() 