import psycopg2
import requests

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

print("🔍 Testing Collection Mapping Logic")
print("=" * 50)

# Test the mapping logic manually
test_path = "/api/v2/tenants/default_tenant/databases/default_database/collections/eb07030e-ed7e-4aab-8249-3a95efefccb0/add"
target_instance = "replica"

print(f"Original path: {test_path}")
print(f"Target instance: {target_instance}")

# Extract collection ID
collection_id = "eb07030e-ed7e-4aab-8249-3a95efefccb0"
print(f"Extracted collection ID: {collection_id}")

# Check database mapping
try:
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Check if we have a mapping for this collection ID
            cur.execute("""
                SELECT collection_name, primary_collection_id, replica_collection_id 
                FROM collection_id_mapping 
                WHERE primary_collection_id = %s OR replica_collection_id = %s
            """, (collection_id, collection_id))
            
            result = cur.fetchone()
            if result:
                collection_name, primary_id, replica_id = result
                print(f"✅ Found mapping: {collection_name}")
                print(f"   Primary ID: {primary_id}")
                print(f"   Replica ID: {replica_id}")
                
                # Apply mapping logic
                target_collection_id = replica_id if target_instance == "replica" else primary_id
                print(f"   Target ID for {target_instance}: {target_collection_id}")
                
                if target_collection_id and target_collection_id != collection_id:
                    mapped_path = test_path.replace(collection_id, target_collection_id)
                    print(f"✅ Should map to: {mapped_path}")
                else:
                    print(f"🔄 No mapping needed")
            else:
                print("❌ No mapping found in database")
                
except Exception as e:
    print(f"❌ Database error: {e}")

# Test load balancer mapping endpoint
print(f"\n🔧 Testing load balancer mapping...")
try:
    response = requests.get("https://chroma-load-balancer.onrender.com/collection/mappings", timeout=30)
    if response.status_code == 200:
        mappings = response.json()
        print(f"Mappings from load balancer: {mappings['count']}")
        for mapping in mappings['mappings']:
            print(f"   {mapping['collection_name']}: {mapping['primary_collection_id'][:8]}... ↔ {mapping['replica_collection_id'][:8]}...")
    else:
        print(f"❌ Mapping endpoint failed: {response.status_code}")
except Exception as e:
    print(f"❌ Load balancer test failed: {e}")

print("\n🧪 Manual path mapping test completed!") 