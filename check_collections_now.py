#!/usr/bin/env python3

import requests
import json

def check_collections():
    print("🔍 CURRENT COLLECTION STATUS")
    print("=" * 50)
    
    try:
        # Check primary
        print("Primary instance:")
        primary = requests.get("https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        
        if primary.status_code == 200:
            primary_colls = primary.json()
            print(f"  Status: {primary.status_code} - {len(primary_colls)} collections")
            for c in primary_colls:
                print(f"    - {c.get('name', 'unnamed')}: {c.get('id', 'no-id')}")
        else:
            print(f"  Status: {primary.status_code}")
        
        # Check replica
        print("\nReplica instance:")
        replica = requests.get("https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        
        if replica.status_code == 200:
            replica_colls = replica.json()
            print(f"  Status: {replica.status_code} - {len(replica_colls)} collections")
            for c in replica_colls:
                print(f"    - {c.get('name', 'unnamed')}: {c.get('id', 'no-id')}")
            if not replica_colls:
                print("    (no collections)")
        else:
            print(f"  Status: {replica.status_code}")
        
        # Check WAL sync status
        print("\nWAL sync status:")
        wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
        if wal_response.status_code == 200:
            wal_status = wal_response.json()
            stats = wal_status['performance_stats']
            print(f"  Successful syncs: {stats['successful_syncs']}")
            print(f"  Failed syncs: {stats['failed_syncs']}")
        else:
            print(f"  WAL status error: {wal_response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_collections() 