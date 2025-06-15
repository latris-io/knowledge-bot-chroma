#!/usr/bin/env python3
"""
Test Unified WAL-First Load Balancer
"""

import sys
sys.path.append('.')

def test_unified_wal():
    print("🚀 Testing Unified WAL-First Load Balancer...")
    
    try:
        from unified_wal_load_balancer import UnifiedWALLoadBalancer
        
        # Initialize unified WAL load balancer
        lb = UnifiedWALLoadBalancer()
        
        # Get status
        status = lb.get_status()
        
        print("✅ Unified WAL Load Balancer initialized successfully!")
        print(f"🏗️  Architecture: {status['architecture']}")
        print(f"📊 Service: {status['service']}")
        print(f"🔄 WAL Sync Interval: {status['unified_wal']['sync_interval_seconds']}s")
        print(f"💾 Approach: {status['unified_wal']['approach']}")
        print(f"🏥 Healthy Instances: {status['healthy_instances']}/{status['total_instances']}")
        
        # Show instance status
        print("\n📍 Instance Status:")
        for instance in status['instances']:
            health_icon = "✅" if instance['healthy'] else "❌"
            print(f"   {health_icon} {instance['name']}: {instance['success_rate']} success rate")
        
        # Show WAL statistics
        wal_info = status['unified_wal']
        print(f"\n📊 Unified WAL Statistics:")
        print(f"   📝 Pending writes: {wal_info['pending_writes']}")
        print(f"   ✅ Executed writes: {wal_info['executed_writes']}")
        print(f"   🔄 Synced writes: {wal_info['synced_writes']}")
        print(f"   ❌ Failed writes: {wal_info['failed_writes']}")
        print(f"   🔄 Is syncing: {wal_info['is_syncing']}")
        
        print("\n🎉 Unified WAL-First Architecture Test PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_unified_wal()
    sys.exit(0 if success else 1) 