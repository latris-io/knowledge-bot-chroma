import psycopg2
import requests
import json

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
primary_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"

print("🔧 FIXING NEW GLOBAL COLLECTION")
print("1. Getting collection details from primary...")

response = requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}", timeout=30)

if response.status_code == 200:
    collection_data = response.json()
    name = collection_data.get('name')
    config = collection_data.get('configuration_json', {})
    print(f"   ✅ Found: {name}")
    
    print("2. Creating on replica...")
    create_response = requests.post(
        "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", 
        headers={"Content-Type": "application/json"}, 
        json={"name": name, "configuration_json": config}, 
        timeout=30
    )
    
    if create_response.status_code in [200, 201]:
        replica_data = create_response.json()
        replica_id = replica_data.get('id')
        print(f"   ✅ Created on replica: {replica_id[:8]}...")
        
        print("3. Updating mapping...")
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE collection_id_mapping SET primary_collection_id = %s, replica_collection_id = %s WHERE collection_name = %s", (primary_id, replica_id, name))
                if cur.rowcount == 0:
                    cur.execute("INSERT INTO collection_id_mapping (collection_name, primary_collection_id, replica_collection_id, collection_config) VALUES (%s, %s, %s, %s)", (name, primary_id, replica_id, json.dumps(config)))
                cur.execute("DELETE FROM unified_wal_writes WHERE status = 'failed' AND path LIKE %s", (f'%{primary_id}%',))
                conn.commit()
        
        print("   ✅ Mapping updated and WAL cleared")
        print("🎉 SUCCESS! Fix completed!")
    else:
        print(f"   ❌ Failed to create on replica: {create_response.status_code}")
        print(f"   Response: {create_response.text}")
else:
    print(f"   ❌ Failed to get from primary: {response.status_code}")
    print(f"   Response: {response.text}") 