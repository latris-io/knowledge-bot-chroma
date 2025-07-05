#!/usr/bin/env python3
"""
DELETE Sync Debugging Script
Gathers comprehensive information for diagnosing DELETE sync issues
"""

import requests
import json
import sys
import argparse
from datetime import datetime

def debug_delete_sync(base_url="https://chroma-load-balancer.onrender.com"):
    """Gather comprehensive DELETE sync debugging information"""
    
    print("🔍 DELETE SYNC DEBUG REPORT")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Base URL: {base_url}")
    print()
    
    # 1. WAL Status
    print("📊 1. WAL SYSTEM STATUS")
    print("-" * 30)
    try:
        wal_response = requests.get(f"{base_url}/wal/status", timeout=10)
        if wal_response.status_code == 200:
            wal_data = wal_response.json()
            print(f"Pending writes: {wal_data.get('pending_writes', 'N/A')}")
            print(f"Failed syncs: {wal_data.get('failed_syncs', 'N/A')}")
            print(f"Successful syncs: {wal_data.get('successful_syncs', 'N/A')}")
        else:
            print(f"❌ WAL status failed: HTTP {wal_response.status_code}")
    except Exception as e:
        print(f"❌ WAL status error: {e}")
    print()
    
    # 2. Recent DELETE Operations in WAL
    print("🗑️ 2. RECENT DELETE OPERATIONS")
    print("-" * 30)
    try:
        wal_debug_response = requests.get(f"{base_url}/admin/wal_debug", timeout=10)
        if wal_debug_response.status_code == 200:
            wal_debug = wal_debug_response.json()
            recent_writes = wal_debug.get('recent_writes', [])
            delete_operations = [w for w in recent_writes if w.get('method') == 'DELETE']
            
            if delete_operations:
                for i, op in enumerate(delete_operations[-5:], 1):  # Last 5 DELETE operations
                    print(f"DELETE #{i}:")
                    print(f"  Write ID: {op.get('write_id', 'N/A')}")
                    print(f"  Path: {op.get('path', 'N/A')}")
                    print(f"  Target: {op.get('target_instance', 'N/A')}")
                    print(f"  Executed on: {op.get('executed_on', 'N/A')}")
                    print(f"  Status: {op.get('status', 'N/A')}")
                    print(f"  Synced instances: {op.get('synced_instances', 'N/A')}")
                    if op.get('error_message'):
                        print(f"  Error: {op.get('error_message')}")
                    print()
            else:
                print("No recent DELETE operations found")
        else:
            print(f"❌ WAL debug failed: HTTP {wal_debug_response.status_code}")
    except Exception as e:
        print(f"❌ WAL debug error: {e}")
    print()
    
    # 3. Collection State on Both Instances
    print("📋 3. COLLECTION STATE VERIFICATION")
    print("-" * 30)
    
    instances = [
        ("Primary", "https://chroma-primary.onrender.com"),
        ("Replica", "https://chroma-replica.onrender.com")
    ]
    
    for instance_name, instance_url in instances:
        print(f"{instance_name} Instance:")
        try:
            collections_response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=10
            )
            if collections_response.status_code == 200:
                collections = collections_response.json()
                test_collections = [c for c in collections if any(pattern in c.get('name', '') 
                                  for pattern in ['TEST', 'MANUAL', 'DELETE', 'UC3'])]
                
                if test_collections:
                    for coll in test_collections:
                        print(f"  - {coll.get('name')} (ID: {coll.get('id', 'N/A')[:8]}...)")
                else:
                    print("  No test collections found")
            else:
                print(f"  ❌ Failed to get collections: HTTP {collections_response.status_code}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
        print()
    
    # 4. Collection Mappings
    print("🗺️ 4. COLLECTION MAPPINGS")
    print("-" * 30)
    try:
        mappings_response = requests.get(f"{base_url}/admin/collection_mappings", timeout=10)
        if mappings_response.status_code == 200:
            mappings_data = mappings_response.json()
            mappings = mappings_data.get('collection_mappings', [])
            test_mappings = [m for m in mappings if any(pattern in m.get('collection_name', '') 
                           for pattern in ['TEST', 'MANUAL', 'DELETE', 'UC3'])]
            
            if test_mappings:
                for mapping in test_mappings:
                    print(f"Collection: {mapping.get('collection_name')}")
                    print(f"  Primary UUID: {mapping.get('primary_collection_id', 'N/A')}")
                    print(f"  Replica UUID: {mapping.get('replica_collection_id', 'N/A')}")
                    print()
            else:
                print("No test collection mappings found")
        else:
            print(f"❌ Mappings failed: HTTP {mappings_response.status_code}")
    except Exception as e:
        print(f"❌ Mappings error: {e}")
    print()
    
    # 5. Transaction Safety Status
    print("🛡️ 5. TRANSACTION SAFETY STATUS")
    print("-" * 30)
    try:
        tx_response = requests.get(f"{base_url}/admin/transaction_safety_status", timeout=10)
        if tx_response.status_code == 200:
            tx_data = tx_response.json()
            print(f"Service running: {tx_data.get('transaction_safety_service', {}).get('running', 'N/A')}")
            print(f"Pending recovery: {tx_data.get('pending_recovery', 'N/A')}")
            print(f"Timing gap failures (24h): {tx_data.get('timing_gap_failures_24h', 'N/A')}")
            
            recent_tx = tx_data.get('recent_transactions', {})
            if recent_tx.get('by_status'):
                print("Recent transaction status:")
                for status_info in recent_tx['by_status']:
                    print(f"  {status_info.get('status')}: {status_info.get('count')} transactions")
        else:
            print(f"❌ Transaction safety failed: HTTP {tx_response.status_code}")
    except Exception as e:
        print(f"❌ Transaction safety error: {e}")
    print()
    
    # 6. System Health
    print("💗 6. SYSTEM HEALTH")
    print("-" * 30)
    try:
        status_response = requests.get(f"{base_url}/status", timeout=10)
        if status_response.status_code == 200:
            status_data = status_response.json()
            print(f"Healthy instances: {status_data.get('healthy_instances', 'N/A')}")
            
            instances_data = status_data.get('instances', {})
            if instances_data:
                for instance_name, instance_info in instances_data.items():
                    print(f"  {instance_name}: {instance_info.get('healthy', 'N/A')}")
        else:
            print(f"❌ Status failed: HTTP {status_response.status_code}")
    except Exception as e:
        print(f"❌ Status error: {e}")
    
    print()
    print("=" * 60)
    print("🔍 DEBUG REPORT COMPLETE")
    print()
    print("💡 TO SHARE WITH DEVELOPER:")
    print("1. Copy the entire output above")
    print("2. Also share load balancer logs from Render dashboard")
    print("3. Include the timeframe when the DELETE sync failure occurred")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DEBUG DELETE sync issues")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", 
                        help="Load balancer URL")
    args = parser.parse_args()
    
    debug_delete_sync(args.url) 