#!/usr/bin/env python3
"""
Test PostgreSQL-backed Write-Ahead Log Implementation
Validates data persistence, recovery, and durability
"""

import os
import json
import uuid
import time
import sys
import requests
from datetime import datetime, timedelta

# Test framework imports
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    print("⚠️ psycopg2 not available - PostgreSQL tests will be skipped")

# Load balancer imports
try:
    from unified_wal_load_balancer import UnifiedWALLoadBalancer, WALEntry
    LOAD_BALANCER_AVAILABLE = True
except ImportError:
    LOAD_BALANCER_AVAILABLE = False
    print("⚠️ unified_wal_load_balancer not available - load balancer tests will be skipped")

# Database configuration
DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

def get_db_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(DATABASE_URL)

def clear_wal_table():
    """Clear WAL table for clean testing"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM wal_pending_writes")
                conn.commit()
                print("🧹 WAL table cleared")
    except Exception as e:
        print(f"❌ Error clearing WAL table: {e}")

def test_postgresql_wal_persistence():
    """Test PostgreSQL WAL data persistence"""
    print("\n🧪 TESTING POSTGRESQL WAL PERSISTENCE")
    print("=" * 50)
    
    # Clear previous test data
    clear_wal_table()
    
    # Test 1: Direct database insertion
    test_id = str(uuid.uuid4())
    test_data = {
        "write_id": test_id,
        "method": "POST",
        "path": "/api/v2/collections",
        "data": b'{"name": "test_collection"}',
        "headers": json.dumps({"Content-Type": "application/json"})
    }
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO wal_pending_writes 
                    (write_id, method, path, data, headers, status)
                    VALUES (%s, %s, %s, %s, %s, 'pending')
                """, (
                    test_data["write_id"],
                    test_data["method"], 
                    test_data["path"],
                    test_data["data"],
                    test_data["headers"]
                ))
                conn.commit()
                
                # Verify insertion
                cur.execute("SELECT COUNT(*) FROM wal_pending_writes WHERE write_id = %s", (test_id,))
                count = cur.fetchone()[0]
                
                if count == 1:
                    print("✅ Test 1: Direct PostgreSQL insertion successful")
                else:
                    print("❌ Test 1: Direct PostgreSQL insertion failed")
                    return False
                    
    except Exception as e:
        print(f"❌ Test 1 Failed: {e}")
        return False
    
    # Test 2: WAL data retrieval
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT write_id, method, path, status, timestamp 
                    FROM wal_pending_writes 
                    WHERE write_id = %s
                """, (test_id,))
                result = cur.fetchone()
                
                if result and result[0] == test_id:
                    print("✅ Test 2: PostgreSQL data retrieval successful")
                    print(f"   📝 Write ID: {result[0][:8]}...")
                    print(f"   🔧 Method: {result[1]}")
                    print(f"   📁 Path: {result[2]}")
                    print(f"   📊 Status: {result[3]}")
                    print(f"   ⏰ Timestamp: {result[4]}")
                else:
                    print("❌ Test 2: PostgreSQL data retrieval failed")
                    return False
                    
    except Exception as e:
        print(f"❌ Test 2 Failed: {e}")
        return False
    
    # Test 3: Status updates
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Mark as completed
                cur.execute("""
                    UPDATE wal_pending_writes 
                    SET status = 'completed', updated_at = NOW()
                    WHERE write_id = %s
                """, (test_id,))
                conn.commit()
                
                # Verify update
                cur.execute("SELECT status FROM wal_pending_writes WHERE write_id = %s", (test_id,))
                status = cur.fetchone()[0]
                
                if status == 'completed':
                    print("✅ Test 3: PostgreSQL status update successful")  
                else:
                    print("❌ Test 3: PostgreSQL status update failed")
                    return False
                    
    except Exception as e:
        print(f"❌ Test 3 Failed: {e}")
        return False
    
    # Test 4: WAL table statistics
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE status = 'pending') as pending,
                        COUNT(*) FILTER (WHERE status = 'completed') as completed,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed
                    FROM wal_pending_writes
                """)
                stats = cur.fetchone()
                
                print("✅ Test 4: PostgreSQL WAL statistics")
                print(f"   📊 Total entries: {stats[0]}")
                print(f"   ⏳ Pending: {stats[1]}")
                print(f"   ✅ Completed: {stats[2]}")
                print(f"   ❌ Failed: {stats[3]}")
                
    except Exception as e:
        print(f"❌ Test 4 Failed: {e}")
        return False
    
    print("\n🎉 ALL POSTGRESQL WAL PERSISTENCE TESTS PASSED")
    return True

def test_load_balancer_integration():
    """Test load balancer PostgreSQL WAL integration"""
    print("\n🧪 TESTING LOAD BALANCER POSTGRESQL INTEGRATION")
    print("=" * 50)
    
    # Import the enhanced load balancer
    try:
        from stable_load_balancer import StableLoadBalancer
        
        # Initialize load balancer
        lb = StableLoadBalancer()
        print("✅ Enhanced load balancer initialized")
        
        # Test database connection
        conn = lb.get_db_connection()
        conn.close()
        print("✅ PostgreSQL connection test successful")
        
        # Test pending writes count
        count = lb.get_pending_writes_count()
        print(f"✅ Pending writes count: {count}")
        
        # Test WAL status query 
        status = lb.get_status()
        if "write_ahead_log" in status:
            wal_info = status["write_ahead_log"]
            print("✅ WAL status integration successful")
            print(f"   📊 Pending writes: {wal_info.get('pending_writes', 0)}")
            print(f"   🔄 Is replaying: {wal_info.get('is_replaying', False)}")
            return True
        else:
            print("❌ WAL status integration failed")
            return False
            
    except Exception as e:
        print(f"❌ Load balancer integration test failed: {e}")
        return False

def test_durability_simulation():
    """Simulate load balancer restart to test durability"""
    print("\n🧪 TESTING WAL DURABILITY SIMULATION")  
    print("=" * 50)
    
    # Clear and add test data
    clear_wal_table()
    
    test_writes = []
    for i in range(3):
        write_id = str(uuid.uuid4())
        test_writes.append(write_id)
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO wal_pending_writes 
                        (write_id, method, path, data, headers, status)
                        VALUES (%s, %s, %s, %s, %s, 'pending')
                    """, (
                        write_id,
                        "POST",
                        f"/api/v2/collections/test_{i}",
                        f'{{"name": "test_collection_{i}"}}'.encode(),
                        json.dumps({"Content-Type": "application/json"})
                    ))
                    conn.commit()
                    
        except Exception as e:
            print(f"❌ Failed to create test write {i}: {e}")
            return False
    
    print(f"✅ Created {len(test_writes)} test writes")
    
    # Simulate "restart" by creating new load balancer instance
    try:
        from stable_load_balancer import StableLoadBalancer
        
        # New instance simulates restart
        lb_after_restart = StableLoadBalancer()
        
        # Check if writes survived "restart"
        surviving_count = lb_after_restart.get_pending_writes_count()
        surviving_writes = lb_after_restart.get_pending_writes()
        
        print(f"✅ After 'restart': {surviving_count} writes survived")
        
        if surviving_count >= len(test_writes):
            print("🎉 DURABILITY TEST PASSED - All writes survived restart!")
            
            # Show details
            for write in surviving_writes[:3]:
                print(f"   📝 {write['write_id'][:8]}... | {write['method']} {write['path']}")
            
            return True
        else:
            print("❌ DURABILITY TEST FAILED - Some writes lost!")
            return False
            
    except Exception as e:
        print(f"❌ Durability test failed: {e}")
        return False

def run_all_tests():
    """Run comprehensive PostgreSQL WAL test suite"""
    print("🚀 POSTGRESQL-BACKED WAL COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("PostgreSQL WAL Persistence", test_postgresql_wal_persistence),
        ("Load Balancer Integration", test_load_balancer_integration), 
        ("Durability Simulation", test_durability_simulation)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        if test_func():
            passed += 1
            print(f"✅ {test_name} PASSED")
        else:
            print(f"❌ {test_name} FAILED")
    
    print("\n" + "=" * 60)
    print(f"📊 FINAL RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - PostgreSQL WAL implementation is ready!")
        return True
    else:
        print("⚠️  Some tests failed - review implementation")
        return False

class TestPostgreSQLWAL:
    """Test PostgreSQL Write-Ahead Log functionality"""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        if not self.database_url:
            # Use default test database URL
            self.database_url = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d46cnlg8fa8c73e5bcs0-a.oregon-postgres.render.com/chroma_ha"
        
        self.connection = None
        self.load_balancer = None
    
    def setup_database(self):
        """Set up database connection and WAL tables"""
        if not POSTGRES_AVAILABLE:
            print("⏭️ Skipping PostgreSQL setup - psycopg2 not available")
            return False
        
        try:
            self.connection = psycopg2.connect(self.database_url)
            print("✅ Connected to PostgreSQL database")
            
            # Create WAL tables using unified system
            if LOAD_BALANCER_AVAILABLE:
                self.load_balancer = UnifiedWALLoadBalancer()
                self.load_balancer.setup_wal_tables()
                print("✅ WAL tables initialized via unified load balancer")
            
            return True
        except Exception as e:
            print(f"❌ Database setup failed: {e}")
            return False

def test_wal_entry_creation():
    """Test WAL entry creation and storage"""
    print("\n🧪 Testing WAL entry creation...")
    
    if not LOAD_BALANCER_AVAILABLE:
        print("⏭️ Skipping WAL entry test - unified_wal_load_balancer not available")
        return True
    
    try:
        # Create test WAL entry
        wal_entry = WALEntry(
            operation_type="add",
            collection_name="test_collection",
            data={"documents": ["test doc"], "ids": ["test_id"]},
            timestamp=datetime.now(),
            source_instance="primary"
        )
        
        print(f"✅ WAL entry created: {wal_entry.operation_type}")
        print(f"  Collection: {wal_entry.collection_name}")
        print(f"  Timestamp: {wal_entry.timestamp}")
        
        return True
    except Exception as e:
        print(f"❌ WAL entry creation failed: {e}")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1) 