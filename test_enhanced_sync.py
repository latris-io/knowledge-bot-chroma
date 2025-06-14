#!/usr/bin/env python3
"""
Test Enhanced Sync Service with Deletion Functionality
"""

import os
import sys
import time
import chromadb
from data_sync_service import ProductionSyncService

def test_enhanced_sync():
    """Test the enhanced sync service including deletion functionality"""
    
    print("🧪 TESTING ENHANCED SYNC SERVICE")
    print("=" * 50)
    
    # Set environment variables for testing
    os.environ["PRIMARY_URL"] = "https://chroma-primary.onrender.com"
    os.environ["REPLICA_URL"] = "https://chroma-replica.onrender.com"
    os.environ["DATABASE_URL"] = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    os.environ["SYNC_INTERVAL"] = "60"  # Short interval for testing
    os.environ["MAX_MEMORY_MB"] = "400"
    os.environ["MAX_WORKERS"] = "1"  # Single worker for testing
    
    try:
        # Initialize sync service
        print("🔧 Initializing sync service...")
        sync_service = ProductionSyncService()
        
        # Test 1: Check connectivity to both instances
        print("\n📡 Testing connectivity...")
        primary_collections = sync_service.get_all_collections("https://chroma-primary.onrender.com")
        replica_collections = sync_service.get_all_collections("https://chroma-replica.onrender.com")
        
        print(f"Primary collections: {len(primary_collections)}")
        print(f"Replica collections: {len(replica_collections)}")
        
        # Test 2: Test deletion sync functionality
        print("\n🗑️ Testing deletion sync...")
        deletion_results = sync_service.sync_deletions()
        
        print(f"Deletion results: {deletion_results}")
        
        # Test 3: Test full sync cycle
        print("\n🔄 Testing full sync cycle...")
        sync_service.perform_production_sync()
        
        print("\n✅ Enhanced sync service test completed successfully!")
        
        # Show final state
        print("\n📊 FINAL STATE:")
        final_primary = sync_service.get_all_collections("https://chroma-primary.onrender.com")
        final_replica = sync_service.get_all_collections("https://chroma-replica.onrender.com")
        
        print(f"Primary: {len(final_primary)} collections")
        print(f"Replica: {len(final_replica)} collections")
        
        if len(final_primary) == len(final_replica):
            print("✅ Primary and replica are in sync!")
        else:
            print(f"⚠️ Sync mismatch: Primary({len(final_primary)}) vs Replica({len(final_replica)})")
            
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_enhanced_sync()
    sys.exit(0 if success else 1) 