#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def fix_collection_auto_creation():
    """Fix the collection auto-creation issue for the new collection"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🔧 FIXING COLLECTION AUTO-CREATION")
    print("=" * 50)
    
    try:
        # Step 1: Get collection details from primary
        primary_collection_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
        print(f"1. Getting collection details from primary: {primary_collection_id[:8]}...")
        
        primary_response = requests.get(
            f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_collection_id}",
            timeout=30
        )
        
        if primary_response.status_code == 200:
            collection_data = primary_response.json()
            collection_name = collection_data.get('name')
            collection_config = collection_data.get('configuration_json', {})
            
            print(f"   ✅ Found collection: '{collection_name}'")
            print(f"   Config: {json.dumps(collection_config)}")
        else:
            print(f"   ❌ Failed to get collection from primary: {primary_response.status_code}")
            return
        
        # Step 2: Create collection on replica
        print("2. Creating collection on replica...")
        
        create_payload = {
            "name": collection_name,
            "configuration_json": collection_config
        }
        
        replica_create_response = requests.post(
            "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        if replica_create_response.status_code in [200, 201]:
            replica_collection = replica_create_response.json()
            replica_collection_id = replica_collection.get('id')
            print(f"   ✅ Created collection on replica: {replica_collection_id[:8]}...")
        else:
            print(f"   ❌ Failed to create collection on replica: {replica_create_response.status_code}")
            print(f"   Response: {replica_create_response.text}")
            return
        
        # Step 3: Create collection mapping in database
        print("3. Creating collection mapping...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO collection_id_mapping 
                    (collection_name, primary_collection_id, replica_collection_id, collection_config)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (collection_name) 
                    DO UPDATE SET 
                        primary_collection_id = EXCLUDED.primary_collection_id,
                        replica_collection_id = EXCLUDED.replica_collection_id,
                        collection_config = EXCLUDED.collection_config,
                        updated_at = NOW()
                """, (
                    collection_name,
                    primary_collection_id,
                    replica_collection_id,
                    json.dumps(collection_config)
                ))
                conn.commit()
                print(f"   ✅ Mapping created: {collection_name}")
                print(f"      Primary: {primary_collection_id[:8]}...")
                print(f"      Replica: {replica_collection_id[:8]}...")
        
        # Step 4: Fix existing WAL entries with new mapping
        print("4. Fixing WAL entries with new collection mapping...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Update failed WAL entries to use correct replica collection ID
                cur.execute("""
                    UPDATE unified_wal_writes 
                    SET path = REPLACE(path, %s, %s), 
                        status = 'executed', 
                        retry_count = 0, 
                        error_message = NULL,
                        updated_at = NOW()
                    WHERE path LIKE %s 
                    AND target_instance = 'replica'
                    AND status = 'failed'
                """, (primary_collection_id, replica_collection_id, f'%{primary_collection_id}%'))
                
                fixed_count = cur.rowcount
                conn.commit()
                print(f"   ✅ Fixed {fixed_count} WAL entries")
        
        # Step 5: Test sync
        print("5. Testing sync after fixes...")
        
        # Wait for sync to process
        for i in range(6):
            time.sleep(5)
            print(f"   Monitoring sync ({(i+1)*5}s)...")
            
            try:
                response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
                if response.status_code == 200:
                    wal_status = response.json()
                    successful = wal_status['performance_stats']['successful_syncs']
                    failed = wal_status['performance_stats']['failed_syncs']
                    print(f"      WAL: {successful} successful, {failed} failed")
                    
                    if successful > 0:
                        print("      🎉 SUCCESS! Sync is working!")
                        break
                else:
                    print(f"      ⚠️ Status check failed: {response.status_code}")
            except Exception as e:
                print(f"      ⚠️ Status check error: {e}")
        
        # Step 6: Final verification
        print("6. Final verification...")
        
        replica_collections = requests.get("https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        if replica_collections.status_code == 200:
            replica_count = len(replica_collections.json())
            print(f"   Replica now has {replica_count} collections")
            
            if replica_count > 0:
                print("   🎉🎉🎉 SUCCESS! COLLECTION AUTO-CREATION WORKING! 🎉🎉🎉")
            else:
                print("   ⚠️ Still need to debug further")
        
        print(f"\n{'='*50}")
        print("🔧 COLLECTION AUTO-CREATION FIX COMPLETED!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    fix_collection_auto_creation() 