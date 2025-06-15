import requests

print("🔍 CHECKING ACTUALLY ACCESSIBLE COLLECTIONS")
print("=" * 50)

# Get primary collections
print("PRIMARY COLLECTIONS:")
primary_response = requests.get("https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
if primary_response.status_code == 200:
    primary_collections = primary_response.json()
    real_primary = []
    for col in primary_collections:
        collection_id = col['id']
        name = col['name']
        # Test if actually accessible
        test_response = requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}", timeout=30)
        status = "✅ REAL" if test_response.status_code == 200 else "❌ PHANTOM"
        print(f"   {name}: {collection_id[:8]}... {status}")
        if test_response.status_code == 200:
            real_primary.append({"name": name, "id": collection_id})
else:
    print(f"   Error: {primary_response.status_code}")

print()
print("REPLICA COLLECTIONS:")
replica_response = requests.get("https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
if replica_response.status_code == 200:
    replica_collections = replica_response.json()
    real_replica = []
    for col in replica_collections:
        collection_id = col['id']
        name = col['name']
        # Test if actually accessible
        test_response = requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}", timeout=30)
        status = "✅ REAL" if test_response.status_code == 200 else "❌ PHANTOM"
        print(f"   {name}: {collection_id[:8]}... {status}")
        if test_response.status_code == 200:
            real_replica.append({"name": name, "id": collection_id})
else:
    print(f"   Error: {replica_response.status_code}")

print()
print("=" * 50)
print("SUMMARY:")
print(f"Real Primary Collections: {len(real_primary) if 'real_primary' in locals() else 0}")
print(f"Real Replica Collections: {len(real_replica) if 'real_replica' in locals() else 0}")

if 'real_primary' in locals() and 'real_replica' in locals():
    if len(real_primary) > 0 and len(real_replica) > 0:
        print("✅ Found real collections on both instances!")
        print("📝 We can use these for working sync")
    elif len(real_primary) > 0:
        print("⚠️ Primary has real collections but replica doesn't")
    elif len(real_replica) > 0:
        print("⚠️ Replica has real collections but primary doesn't")
    else:
        print("❌ No real collections found - major database issue") 