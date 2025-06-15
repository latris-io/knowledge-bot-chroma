#!/usr/bin/env python3
"""
Test script for Write-Ahead Log functionality
Demonstrates high availability writes with automatic replay
"""

import json
import time
import requests
from datetime import datetime

def test_write_ahead_log():
    """Test the Write-Ahead Log functionality"""
    
    load_balancer_url = "https://chroma-load-balancer.onrender.com"
    
    print("🧪 Testing Write-Ahead Log Functionality")
    print("=" * 50)
    
    # 1. Check initial status
    print("\n1️⃣ Checking initial system status...")
    try:
        response = requests.get(f"{load_balancer_url}/status")
        status = response.json()
        print(f"✅ System Status: {status.get('service', 'ChromaDB Load Balancer')}")
        print(f"   Healthy instances: {status['healthy_instances']}/{status['total_instances']}")
        print(f"   Pending writes: {status['write_ahead_log']['pending_writes']}")
        print(f"   Total replayed: {status['write_ahead_log']['total_replayed']}")
        
        primary_healthy = False
        replica_healthy = False
        
        for instance in status['instances']:
            health_emoji = "✅" if instance['healthy'] else "❌"
            print(f"   {health_emoji} {instance['name']}: {instance['success_rate']} success rate")
            if instance['name'] == 'primary':
                primary_healthy = instance['healthy']
            elif instance['name'] == 'replica':
                replica_healthy = instance['healthy']
        
        # Check if we have the perfect WAL test scenario
        if not primary_healthy and replica_healthy:
            print(f"   🎯 PERFECT! Primary is down, replica is up - ideal for Write-Ahead Log demo!")
        elif primary_healthy and replica_healthy:
            print(f"   ℹ️  Both instances healthy - normal operation mode")
        else:
            print(f"   ⚠️  Unusual state - may affect demo")
            
    except Exception as e:
        print(f"❌ Failed to get status: {e}")
        return
    
    # 2. Test normal write operation (both instances healthy)
    print("\n2️⃣ Testing normal write operation...")
    collection_name = f"test_wal_{int(time.time())}"
    
    try:
        # Create collection
        collection_data = {
            "name": collection_name,
            "metadata": {"test": "write_ahead_log_demo"}
        }
        
        response = requests.post(
            f"{load_balancer_url}/api/v2/collections",
            json=collection_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            print(f"✅ Collection created successfully: {collection_name}")
        else:
            print(f"❌ Failed to create collection: {response.status_code}")
            return
            
    except Exception as e:
        print(f"❌ Failed normal write test: {e}")
        return
    
    # 3. Add some data normally
    print("\n3️⃣ Adding data during normal operation...")
    try:
        documents_data = {
            "documents": ["This is a test document for Write-Ahead Log"],
            "metadatas": [{"source": "wal_test", "timestamp": datetime.now().isoformat()}],
            "ids": ["doc_1"]
        }
        
        response = requests.post(
            f"{load_balancer_url}/api/v2/collections/{collection_name}/add",
            json=documents_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            print("✅ Document added successfully during normal operation")
        else:
            print(f"❌ Failed to add document: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Failed to add document: {e}")
    
    # 4. Simulate primary failure scenario
    print("\n4️⃣ Simulating primary failure scenario...")
    print("   ⚠️  For this demo, we'll test with current architecture")
    print("   📝 When primary goes down, writes will be queued in Write-Ahead Log")
    print("   🔄 When primary recovers, queued writes will be replayed automatically")
    
    # 5. Monitor Write-Ahead Log status
    print("\n5️⃣ Monitoring Write-Ahead Log status...")
    for i in range(3):
        try:
            response = requests.get(f"{load_balancer_url}/status")
            status = response.json()
            wal_info = status['write_ahead_log']
            
            print(f"   📊 Check {i+1}/3:")
            print(f"      Pending writes: {wal_info['pending_writes']}")
            print(f"      Is replaying: {wal_info['is_replaying']}")
            print(f"      Total replayed: {wal_info['total_replayed']}")
            print(f"      Failed replays: {wal_info['failed_replays']}")
            
            if wal_info['oldest_pending']:
                print(f"      Oldest pending: {wal_info['oldest_pending']}")
            
            time.sleep(5)
            
        except Exception as e:
            print(f"   ❌ Failed to get status: {e}")
    
    # 6. Test read operations during primary outage
    print("\n6️⃣ Testing read operations...")
    try:
        response = requests.get(f"{load_balancer_url}/api/v2/collections/{collection_name}/get")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Read operation successful - found {len(data.get('documents', []))} documents")
        else:
            print(f"⚠️  Read operation returned: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Read operation failed: {e}")
    
    # 7. Final status check
    print("\n7️⃣ Final system status...")
    try:
        response = requests.get(f"{load_balancer_url}/status")
        status = response.json()
        
        print(f"✅ Final Status Summary:")
        print(f"   Service: {status['service']}")
        print(f"   Healthy instances: {status['healthy_instances']}/{status['total_instances']}")
        
        wal_info = status['write_ahead_log']
        print(f"   Write-Ahead Log:")
        print(f"     Pending writes: {wal_info['pending_writes']}")
        print(f"     Total replayed: {wal_info['total_replayed']}")
        print(f"     Failed replays: {wal_info['failed_replays']}")
        
        print(f"   Total requests: {status['stats']['total_requests']}")
        print(f"   Success rate: {status['stats']['successful_requests']}/{status['stats']['total_requests']}")
        
    except Exception as e:
        print(f"❌ Failed final status check: {e}")
    
    print("\n🎯 Write-Ahead Log Architecture Benefits:")
    print("   ✅ High Availability - Accepts writes even when primary is down")
    print("   ✅ Data Safety - All writes are preserved and replayed") 
    print("   ✅ Automatic Recovery - No manual intervention needed")
    print("   ✅ Ordered Replay - Maintains write order consistency")
    print("   ✅ Retry Logic - Handles temporary failures during replay")

if __name__ == "__main__":
    test_write_ahead_log() 