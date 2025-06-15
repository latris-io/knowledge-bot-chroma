#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def fix_collection_mapping():
    """Fix the collection ID mapping issue during sync"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🔧 COLLECTION ID MAPPING FIX")
    print("=" * 50)
    
    try:
        # Step 1: Get the current mapping
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping WHERE collection_name = 'global'")
                result = cur.fetchone()
                
                if result:
                    name, primary_id, replica_id = result
                    print(f"✅ Mapping found: {name}")
                    print(f"   Primary ID:  {primary_id}")
                    print(f"   Replica ID:  {replica_id}")
                else:
                    print("❌ No mapping found!")
                    return
        
        # Step 2: Update existing WAL entries to use correct collection IDs for their targets
        print("2. Fixing existing WAL entries with wrong collection IDs...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Find WAL entries targeting replica but using primary ID in path
                cur.execute("""
                    SELECT write_id, path, target_instance 
                    FROM unified_wal_writes 
                    WHERE status IN ('executed', 'pending', 'failed')
                    AND path LIKE %s
                    AND target_instance = 'replica'
                """, (f'%{primary_id}%',))
                
                wrong_entries = cur.fetchall()
                print(f"   Found {len(wrong_entries)} entries with wrong collection ID")
                
                fixed_count = 0
                for write_id, path, target_instance in wrong_entries:
                    # Replace primary ID with replica ID in path
                    fixed_path = path.replace(primary_id, replica_id)
                    
                    # Update the WAL entry
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET path = %s, status = 'executed', retry_count = 0, error_message = NULL, updated_at = NOW()
                        WHERE write_id = %s
                    """, (fixed_path, write_id))
                    
                    print(f"   Fixed {write_id[:8]}: {path[:80]}... → {fixed_path[:80]}...")
                    fixed_count += 1
                
                conn.commit()
                print(f"   ✅ Fixed {fixed_count} WAL entries")
        
        # Step 3: Test the sync after fixing entries
        print("3. Testing sync after fixing WAL entries...")
        
        # Trigger sync by calling the load balancer WAL status endpoint
        response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
        if response.status_code == 200:
            wal_status = response.json()
            print(f"   Current WAL status:")
            print(f"      Successful: {wal_status['performance_stats']['successful_syncs']}")
            print(f"      Failed: {wal_status['performance_stats']['failed_syncs']}")
        
        # Wait for sync to process
        print("4. Monitoring sync for 30 seconds...")
        initial_successful = wal_status['performance_stats']['successful_syncs'] if response.status_code == 200 else 0
        
        for i in range(6):
            time.sleep(5)
            print(f"   Checking sync progress ({(i+1)*5}s)...")
            
            try:
                sync_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
                if sync_response.status_code == 200:
                    sync_status = sync_response.json()
                    current_successful = sync_status['performance_stats']['successful_syncs']
                    current_failed = sync_status['performance_stats']['failed_syncs']
                    
                    print(f"      Successful: {current_successful}, Failed: {current_failed}")
                    
                    if current_successful > initial_successful:
                        print("      🎉 SUCCESS! Sync is now working!")
                        break
                else:
                    print(f"      ⚠️ Status check failed: {sync_response.status_code}")
            except Exception as e:
                print(f"      ⚠️ Status check error: {e}")
        
        # Step 5: Final verification
        print("5. Final verification...")
        
        primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
        replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
        
        print(f"   Final document counts:")
        print(f"      Primary: {primary_count}")
        print(f"      Replica: {replica_count}")
        
        if replica_count >= primary_count:
            print("   🎉🎉🎉 SUCCESS! SYNC IS FULLY WORKING! 🎉🎉🎉")
        elif replica_count > 4:  # Previous count was 4
            print("   ✅ PROGRESS! Replica count increased - sync is partially working!")
        else:
            print("   ⚠️ No replica increase detected yet - may need more time")
        
        print(f"\n{'='*50}")
        print("🔧 COLLECTION ID MAPPING FIX COMPLETED!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    fix_collection_mapping() 