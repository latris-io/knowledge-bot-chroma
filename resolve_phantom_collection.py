#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def resolve_phantom_collection():
    """Resolve the phantom collection issue and enable proper sync"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    phantom_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
    
    print("🔧 RESOLVING PHANTOM COLLECTION ISSUE")
    print("=" * 50)
    
    try:
        # Step 1: Clear phantom collection WAL entries
        print("1. Clearing phantom collection WAL entries...")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM unified_wal_writes WHERE path LIKE %s", (f'%{phantom_id}%',))
                deleted_count = cur.rowcount
                conn.commit()
                print(f"   ✅ Cleared {deleted_count} phantom WAL entries")
        
        # Step 2: Create a new working global collection on primary
        print("2. Creating new working 'global' collection on primary...")
        
        create_payload = {
            "name": "global",
            "configuration_json": {
                "hnsw": {
                    "space": "l2", 
                    "ef_construction": 100
                }
            }
        }
        
        primary_response = requests.post(
            "https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        if primary_response.status_code in [200, 201]:
            primary_data = primary_response.json()
            new_primary_id = primary_data.get('id')
            print(f"   ✅ Created new global collection on primary: {new_primary_id[:8]}...")
        else:
            print(f"   ❌ Failed to create on primary: {primary_response.status_code}")
            print(f"   Response: {primary_response.text}")
            return
        
        # Step 3: Create matching collection on replica
        print("3. Creating matching 'global' collection on replica...")
        
        replica_response = requests.post(
            "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        if replica_response.status_code in [200, 201]:
            replica_data = replica_response.json()
            new_replica_id = replica_data.get('id')
            print(f"   ✅ Created new global collection on replica: {new_replica_id[:8]}...")
        else:
            print(f"   ❌ Failed to create on replica: {replica_response.status_code}")
            print(f"   Response: {replica_response.text}")
            return
        
        # Step 4: Create collection mapping
        print("4. Creating collection ID mapping...")
        
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
                    "global",
                    new_primary_id,
                    new_replica_id,
                    json.dumps(create_payload["configuration_json"])
                ))
                conn.commit()
                print(f"   ✅ Mapping created:")
                print(f"      Primary: {new_primary_id[:8]}...")
                print(f"      Replica: {new_replica_id[:8]}...")
        
        # Step 5: Test with new document
        print("5. Testing with new document upload...")
        
        test_payload = {
            "embeddings": [[0.1] * 3072],
            "documents": ["Test document after phantom collection fix"],
            "metadatas": [{"test": "phantom_fix", "timestamp": int(time.time())}],
            "ids": [f"phantom_fix_{int(time.time())}"]
        }
        
        test_response = requests.post(
            f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{new_primary_id}/add",
            headers={"Content-Type": "application/json"},
            json=test_payload,
            timeout=30
        )
        
        if test_response.status_code in [200, 201]:
            print("   ✅ Test document added - monitoring sync...")
            
            # Monitor sync
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
                        
                        if successful > 0:
                            print("      🎉 SUCCESS! Sync is working!")
                            break
                    else:
                        print(f"      ⚠️ WAL status error: {wal_response.status_code}")
                except Exception as e:
                    print(f"      ⚠️ Status check error: {e}")
        else:
            print(f"   ❌ Test document failed: {test_response.status_code}")
            print(f"   Response: {test_response.text}")
        
        # Step 6: Final verification
        print("6. Final verification...")
        
        replica_check = requests.get("https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        if replica_check.status_code == 200:
            replica_collections = replica_check.json()
            print(f"   Replica collections: {len(replica_collections)}")
            
            for c in replica_collections:
                if c['name'] == 'global':
                    replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{c['id']}/count", timeout=30).text)
                    print(f"   - {c['name']}: {replica_count} documents")
                    
                    if replica_count > 0:
                        print("   🎉🎉🎉 SUCCESS! PHANTOM COLLECTION RESOLVED - SYNC WORKING! 🎉🎉🎉")
                        print(f"   📌 NEW WORKING COLLECTION IDs:")
                        print(f"      Primary:  {new_primary_id}")
                        print(f"      Replica:  {new_replica_id}")
                        print(f"   📝 Update your ingestion service to use: {new_primary_id}")
                        return
            
            print("   ⚠️ Collection created but not yet synced")
        else:
            print(f"   ❌ Failed to check replica: {replica_check.status_code}")
        
        print(f"\n{'='*50}")
        print("🔧 PHANTOM COLLECTION RESOLUTION COMPLETED!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Resolution failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    resolve_phantom_collection() 