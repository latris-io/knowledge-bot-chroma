#!/usr/bin/env python3
"""
Sync Status Verification
========================
Check if primary and replica are properly synchronized
"""

import requests
import json

PRIMARY_URL = "https://chroma-primary.onrender.com"
REPLICA_URL = "https://chroma-replica.onrender.com"
LOAD_BALANCER_URL = "https://chroma-load-balancer.onrender.com"

def get_collections(instance_url, instance_name):
    """Get collections from an instance"""
    try:
        response = requests.get(f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections")
        if response.status_code == 200:
            collections = response.json()
            print(f"📊 {instance_name}: {len(collections)} collections")
            for col in collections:
                count_response = requests.get(f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{col['id']}/count")
                count = count_response.json() if count_response.status_code == 200 else "?"
                print(f"   • {col['name']}: {count} documents")
            return collections
        else:
            print(f"❌ Failed to get collections from {instance_name}: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error getting collections from {instance_name}: {e}")
        return []

def check_load_balancer_health():
    """Check load balancer health status"""
    try:
        response = requests.get(f"{LOAD_BALANCER_URL}/health")
        if response.status_code == 200:
            health = response.json()
            print(f"🏥 Load Balancer Health: {health.get('status', 'unknown')}")
            print(f"   • Healthy instances: {health.get('healthy_instances', 'unknown')}")
            print(f"   • Pending writes: {health.get('pending_writes', 'unknown')}")
            print(f"   • Architecture: {health.get('architecture', 'unknown')}")
            return True
    except Exception as e:
        print(f"❌ Load balancer health check failed: {e}")
        return False

def main():
    print("🔍 SYNC STATUS VERIFICATION")
    print("=" * 40)
    
    # Check load balancer health
    print("\n🏥 Load Balancer Status:")
    check_load_balancer_health()
    
    # Check collections on both instances
    print(f"\n📋 Collection Status:")
    primary_collections = get_collections(PRIMARY_URL, "Primary")
    replica_collections = get_collections(REPLICA_URL, "Replica")
    
    # Compare collections
    print(f"\n🔄 Sync Analysis:")
    if len(primary_collections) == len(replica_collections):
        print("✅ Collection count matches")
        
        # Check individual collection document counts
        primary_by_name = {col['name']: col for col in primary_collections}
        replica_by_name = {col['name']: col for col in replica_collections}
        
        all_synced = True
        for name in primary_by_name.keys():
            if name in replica_by_name:
                p_count = requests.get(f"{PRIMARY_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_by_name[name]['id']}/count").json()
                r_count = requests.get(f"{REPLICA_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_by_name[name]['id']}/count").json()
                
                if p_count == r_count:
                    print(f"   ✅ {name}: {p_count} docs (synced)")
                else:
                    print(f"   ❌ {name}: Primary({p_count}) ≠ Replica({r_count})")
                    all_synced = False
            else:
                print(f"   ❌ {name}: Missing in replica")
                all_synced = False
        
        if all_synced:
            print("\n🎉 ALL DATA IS SYNCHRONIZED!")
        else:
            print("\n⚠️ SYNC ISSUES DETECTED")
            print("\n💡 To fix sync issues:")
            print("1. Ensure your data loader uses: https://chroma-load-balancer.onrender.com")
            print("2. Re-ingest any missing data through the load balancer")
            print("3. The WAL system will automatically sync new data")
    else:
        print(f"❌ Collection count mismatch: Primary({len(primary_collections)}) vs Replica({len(replica_collections)})")
    
    print(f"\n💡 IMPORTANT: Always use the load balancer URL for data operations:")
    print(f"   {LOAD_BALANCER_URL}")

if __name__ == "__main__":
    main() 