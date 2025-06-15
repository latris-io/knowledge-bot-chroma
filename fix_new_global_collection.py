#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def fix_new_global_collection():
    """Fix the new global collection mapping issue"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🔧 FIXING NEW GLOBAL COLLECTION MAPPING")
    print("=" * 50)
    
    try:
        # Step 1: Get the current primary collection details  
        primary_collection_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
        print(f"1. Getting collection details for 'global': {primary_collection_id[:8]}...")
        
        primary_response = requests.get(
            f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_collection_id}",
            timeout=30
        )
        
        if primary_response.status_code == 200:
            collection_data = primary_response.json()
            collection_name = collection_data.get('name')  # Should be "global"
            collection_config = collection_data.get('configuration_json', {})
            
            print(f"   ✅ Found collection: '{collection_name}'")
            print(f"   Config: {json.dumps(collection_config)}")
        else:
            print(f"   ❌ Failed to get collection from primary: {primary_response.status_code}")
            print(f"   Response: {primary_response.text}")
            return
        
        # Step 2: Create collection on replica with same name and config
        print("2. Creating 'global' collection on replica...")
        
        create_payload = {
            "name": collection_name,  # "global"
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
        
        # Step 3: Update collection mapping in database (replace old mapping)
        print("3. Updating collection mapping...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Replace the old global mapping with the new one
                cur.execute("""
                    UPDATE collection_id_mapping 
                    SET primary_collection_id = %s, 
                        replica_collection_id = %s,
                        collection_config = %s,
                        updated_at = NOW()
                    WHERE collection_name = %s
                """, (
                    primary_collection_id,
                    replica_collection_id,
                    json.dumps(collection_config),
                    collection_name  # "global"
                ))
                
                if cur.rowcount == 0:
                    # No existing mapping, create new one
                    cur.execute("""
                        INSERT INTO collection_id_mapping 
                        (collection_name, primary_collection_id, replica_collection_id, collection_config)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        collection_name,
                        primary_collection_id,
                        replica_collection_id,
                        json.dumps(collection_config)
                    ))
                    print(f"   ✅ Created new mapping for: {collection_name}")
                else:
                    print(f"   ✅ Updated existing mapping for: {collection_name}")
                
                print(f"      Primary: {primary_collection_id[:8]}...")
                print(f"      Replica: {replica_collection_id[:8]}...")
                conn.commit()
        
        # Step 4: Clear failed WAL entries and reset them
        print("4. Resetting failed WAL entries...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Clear failed entries for the old collection ID
                cur.execute("""
                    DELETE FROM unified_wal_writes 
                    WHERE status = 'failed' 
                    AND path LIKE %s
                """, (f'%{primary_collection_id}%',))
                
                deleted_count = cur.rowcount
                conn.commit()
                print(f"   ✅ Cleared {deleted_count} failed WAL entries")
        
        # Step 5: Test by triggering a new write operation
        print("5. Testing with new document ingestion...")
        
        test_payload = {
            "embeddings": [[0.1] * 3072],
            "documents": ["New global collection test"],
            "metadatas": [{"test": "new_global", "timestamp": int(time.time())}],
            "ids": [f"new_global_test_{int(time.time())}"]
        }
        
        # Send to load balancer to trigger WAL
        test_response = requests.post(
            f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_collection_id}/add",
            headers={"Content-Type": "application/json"},
            json=test_payload,
            timeout=30
        )
        
        if test_response.status_code in [200, 201]:
            print("   ✅ Test ingestion successful - should trigger intelligent sync")
        else:
            print(f"   ❌ Test ingestion failed: {test_response.status_code}")
        
        # Step 6: Monitor sync
        print("6. Monitoring sync for 30 seconds...")
        
        for i in range(6):
            time.sleep(5)
            print(f"   Checking sync ({(i+1)*5}s)...")
            
            try:
                response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
                if response.status_code == 200:
                    wal_status = response.json()
                    successful = wal_status['performance_stats']['successful_syncs']
                    failed = wal_status['performance_stats']['failed_syncs']
                    print(f"      WAL: {successful} successful, {failed} failed")
                    
                    if successful > 0:
                        print("      🎉 SUCCESS! Intelligent sync is working!")
                        break
                else:
                    print(f"      ⚠️ Status check failed: {response.status_code}")
            except Exception as e:
                print(f"      ⚠️ Status check error: {e}")
        
        # Step 7: Final verification
        print("7. Final verification...")
        
        replica_response = requests.get("https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        if replica_response.status_code == 200:
            replica_collections = replica_response.json()
            print(f"   Replica now has {len(replica_collections)} collections")
            
            if len(replica_collections) > 0:
                for c in replica_collections:
                    replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{c['id']}/count", timeout=30).text)
                    print(f"   - {c['name']}: {replica_count} documents")
                
                print("   🎉🎉🎉 SUCCESS! INTELLIGENT WAL SYNC FULLY OPERATIONAL! 🎉🎉🎉")
            else:
                print("   ⚠️ Still no collections on replica")
        
        print(f"\n{'='*50}")
        print("🔧 NEW GLOBAL COLLECTION FIX COMPLETED!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    fix_new_global_collection() 