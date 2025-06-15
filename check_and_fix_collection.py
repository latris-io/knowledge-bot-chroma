import requests
import psycopg2
import json

def check_and_fix_collection():
    collection_id = "bdb93852-54be-47b4-ae9c-43fb90a9dea7"
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🔍 CHECKING AND FIXING COLLECTION AUTO-CREATION")
    print(f"Collection ID: {collection_id}")
    print("=" * 50)
    
    # Check if collection exists on primary
    print("1. Checking collection on primary...")
    response = requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}", timeout=30)
    
    print(f"   Primary status: {response.status_code}")
    
    if response.status_code == 200:
        collection_data = response.json()
        collection_name = collection_data.get('name')
        collection_config = collection_data.get('configuration_json', {})
        
        print(f"   ✅ Collection exists: '{collection_name}'")
        print(f"   Config: {collection_config}")
        
        # Create collection on replica
        print("2. Creating collection on replica...")
        
        create_payload = {
            "name": collection_name,
            "configuration_json": collection_config
        }
        
        replica_response = requests.post(
            "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        print(f"   Replica creation: {replica_response.status_code}")
        
        if replica_response.status_code in [200, 201]:
            replica_data = replica_response.json()
            replica_id = replica_data.get('id')
            print(f"   ✅ Created on replica: {replica_id}")
            
            # Create mapping
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
                            collection_config = EXCLUDED.collection_config
                    """, (collection_name, collection_id, replica_id, json.dumps(collection_config)))
                    
                    # Reset failed WAL entries
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET status = 'executed', retry_count = 0, error_message = NULL, updated_at = NOW()
                        WHERE status = 'failed' AND path LIKE %s
                    """, (f'%{collection_id}%',))
                    
                    fixed_count = cur.rowcount
                    conn.commit()
                    
            print(f"   ✅ Mapping created and {fixed_count} WAL entries reset")
            print("🎉 SUCCESS! Collection auto-creation completed!")
            
        else:
            print(f"   ❌ Failed to create on replica: {replica_response.text}")
    else:
        print(f"   ❌ Collection not found on primary: {response.text}")

if __name__ == "__main__":
    check_and_fix_collection() 