import requests

collection_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
print("🔍 TESTING CORRECT COLLECTION ENDPOINTS")
print("=" * 50)

# Test the /get endpoint (what user uses successfully)
print("1. Testing /get endpoint (user's working method)...")
get_response = requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get", timeout=30)
print(f"   GET /get endpoint: {get_response.status_code}")

# Test count endpoint
print("2. Testing /count endpoint...")
count_response = requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/count", timeout=30)
print(f"   GET /count endpoint: {count_response.status_code}")
if count_response.status_code == 200:
    print(f"   Document count: {count_response.text}")

# Test the endpoint I was using (direct collection access)
print("3. Testing direct collection access (my method)...")
direct_response = requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}", timeout=30)
print(f"   GET direct collection: {direct_response.status_code}")

print()
print("ANALYSIS:")
if get_response.status_code == 200:
    print("✅ Collection IS accessible via /get endpoint!")
    print("❌ My 'phantom collection' diagnosis was WRONG!")
    print("🔧 The issue is NOT phantom collections")
    print("🔍 Need to investigate actual sync failure cause")
else:
    print("❌ Collection still has accessibility issues")

print()
print("TESTING REPLICA COLLECTION:")
replica_id = "0c6ab3d3-bbf2-44e4-9cfe-e95654c43ace"  # Original replica mapping

replica_get = requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/get", timeout=30)
print(f"Replica /get endpoint: {replica_get.status_code}")

replica_count = requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30)
print(f"Replica /count endpoint: {replica_count.status_code}")
if replica_count.status_code == 200:
    print(f"Replica document count: {replica_count.text}")

if replica_get.status_code == 200:
    print("✅ REPLICA COLLECTION ALSO ACCESSIBLE!")
    print("🎯 Both collections exist - sync issue is elsewhere!")
else:
    print("❌ Replica collection has issues") 