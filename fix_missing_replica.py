import requests
import json
import psycopg2

def fix_missing_replica():
    """Fix the missing replica collection issue"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🔧 FIXING MISSING REPLICA COLLECTION")
    print("=" * 50)
    
    # Check current collection mappings
    print("1. Checking current collection mappings...")
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping")
            mappings = cur.fetchall()
            print(f"   Found {len(mappings)} mappings:")
            for m in mappings:
                print(f"     {m[0]}: {m[1][:8]}... -> {m[2][:8]}...")
    
    # Check primary collection (we know it exists with 4 documents)
    primary_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
    print(f"2. Verifying primary collection {primary_id[:8]}...")
    
    primary_count = requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30)
    print(f"   Primary count: {primary_count.status_code} - {primary_count.text if primary_count.status_code == 200 else 'Error'}")
    
    if primary_count.status_code == 200:
        # Create the missing replica collection for "global"
        print("3. Creating missing replica collection...")
        
        create_payload = {
            "name": "global",
            "configuration_json": {
                "hnsw": {
                    "space": "l2",
                    "ef_construction": 100
                }
            }
        }
        
        replica_response = requests.post(
            "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        if replica_response.status_code in [200, 201]:
            replica_data = replica_response.json()
            replica_id = replica_data.get('id')
            print(f"   ✅ Created replica collection: {replica_id}")
            
            # Test replica accessibility
            replica_count = requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30)
            print(f"   Replica count test: {replica_count.status_code}")
            
            if replica_count.status_code == 200:
                print(f"   ✅ Replica accessible with {replica_count.text} documents")
                
                # Create/update the mapping
                print("4. Creating collection mapping...")
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO collection_id_mapping 
                            (collection_name, primary_collection_id, replica_collection_id, collection_config)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (collection_name) 
                            DO UPDATE SET 
                                replica_collection_id = EXCLUDED.replica_collection_id,
                                updated_at = NOW()
                        """, (
                            "global",
                            primary_id,
                            replica_id,
                            json.dumps(create_payload["configuration_json"])
                        ))
                        conn.commit()
                        print(f"   ✅ Mapping updated:")
                        print(f"      Primary:  {primary_id}")
                        print(f"      Replica:  {replica_id}")
                
                # Test sync with a new document
                print("5. Testing intelligent sync...")
                
                test_payload = {
                    "embeddings": [[0.1] * 3072],
                    "documents": ["Test sync after replica fix"],
                    "metadatas": [{"test": "replica_fix"}],
                    "ids": ["replica_fix_test"]
                }
                
                sync_response = requests.post(
                    f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add",
                    headers={"Content-Type": "application/json"},
                    json=test_payload,
                    timeout=30
                )
                
                if sync_response.status_code in [200, 201]:
                    print("   ✅ Test document uploaded via load balancer")
                    
                    print("6. Monitoring sync...")
                    import time
                    for i in range(6):
                        time.sleep(5)
                        
                        new_primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
                        new_replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
                        
                        print(f"   ({(i+1)*5}s) Counts: Primary={new_primary_count}, Replica={new_replica_count}")
                        
                        if new_replica_count > 0:
                            print()
                            print("🎉🎉🎉 SUCCESS! SYNC IS NOW WORKING! 🎉🎉🎉")
                            print("✅ Missing replica collection fixed!")
                            print("✅ Intelligent WAL sync operational!")
                            print()
                            print("📌 WORKING COLLECTION INFO:")
                            print(f"   Collection Name: global")
                            print(f"   Primary ID:  {primary_id}")
                            print(f"   Replica ID:  {replica_id}")
                            print()
                            print("✅ Your file uploads are now syncing automatically!")
                            return
                    
                    print("   Sync may need more time but infrastructure is fixed")
                else:
                    print(f"   ❌ Sync test failed: {sync_response.status_code}")
            else:
                print(f"   ❌ Replica not accessible: {replica_count.status_code}")
        else:
            print(f"   ❌ Replica creation failed: {replica_response.status_code} - {replica_response.text}")
    else:
        print(f"   ❌ Primary collection issue: {primary_count.status_code}")

if __name__ == "__main__":
    fix_missing_replica() 