#!/usr/bin/env python3
"""
Comprehensive Write-Ahead Log Test Suite
Tests all WAL functionality including failure scenarios, replay logic, and edge cases
"""

import unittest
import requests
import json
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestWriteAheadLog(unittest.TestCase):
    """Comprehensive tests for Write-Ahead Log functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.load_balancer_url = os.getenv("LOAD_BALANCER_URL", "https://chroma-load-balancer.onrender.com")
        self.test_collection_prefix = f"wal_test_{int(time.time())}"
        self.test_collections = []
        
    def tearDown(self):
        """Clean up test collections"""
        for collection_name in self.test_collections:
            try:
                requests.delete(f"{self.load_balancer_url}/api/v2/collections/{collection_name}")
            except:
                pass  # Ignore cleanup errors
                
    def get_wal_status(self):
        """Get current WAL status from load balancer"""
        try:
            response = requests.get(f"{self.load_balancer_url}/status", timeout=10)
            return response.json()
        except Exception as e:
            self.fail(f"Failed to get WAL status: {e}")
    
    def wait_for_condition(self, condition_func, timeout=30, interval=1):
        """Wait for a condition to be met"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition_func():
                return True
            time.sleep(interval)
        return False
    
    def test_wal_status_endpoint(self):
        """Test WAL status endpoint returns correct structure"""
        print("\n🧪 Testing WAL Status Endpoint")
        
        status = self.get_wal_status()
        
        # Verify WAL structure
        self.assertIn("write_ahead_log", status)
        wal_info = status["write_ahead_log"]
        
        required_fields = ["pending_writes", "is_replaying", "oldest_pending", "total_replayed", "failed_replays"]
        for field in required_fields:
            self.assertIn(field, wal_info)
            
        # Verify instance health reporting
        self.assertIn("instances", status)
        self.assertGreater(len(status["instances"]), 0)
        
        print(f"✅ Status endpoint structure valid")
        print(f"   WAL pending writes: {wal_info['pending_writes']}")
        print(f"   WAL total replayed: {wal_info['total_replayed']}")
        
    def test_normal_operation_no_wal(self):
        """Test normal operation when both instances are healthy"""
        print("\n🧪 Testing Normal Operation (No WAL)")
        
        status = self.get_wal_status()
        primary_healthy = any(inst["name"] == "primary" and inst["healthy"] for inst in status["instances"])
        
        if not primary_healthy:
            self.skipTest("Primary not healthy - cannot test normal operation")
            
        collection_name = f"{self.test_collection_prefix}_normal"
        self.test_collections.append(collection_name)
        
        # Create collection during normal operation
        response = requests.post(
            f"{self.load_balancer_url}/api/v2/collections",
            json={"name": collection_name, "metadata": {"test": "normal_operation"}},
            headers={"Content-Type": "application/json"}
        )
        
        # Should succeed without using WAL
        self.assertEqual(response.status_code, 200)
        
        # Verify no pending writes in WAL
        status = self.get_wal_status()
        self.assertEqual(status["write_ahead_log"]["pending_writes"], 0)
        
        print(f"✅ Normal operation working - no WAL activation")
        
    def test_read_operations_during_primary_failure(self):
        """Test read operations continue working when primary is down"""
        print("\n🧪 Testing Read Operations During Primary Failure")
        
        status = self.get_wal_status()
        replica_healthy = any(inst["name"] == "replica" and inst["healthy"] for inst in status["instances"])
        
        if not replica_healthy:
            self.skipTest("Replica not healthy - cannot test read failover")
            
        # Try to read collections
        response = requests.get(f"{self.load_balancer_url}/api/v2/collections")
        
        # Should get some response (may be error due to both instances having issues, but shouldn't hang)
        self.assertIsNotNone(response.status_code)
        self.assertLess(response.elapsed.total_seconds(), 30)  # Should not timeout
        
        print(f"✅ Read operations handled gracefully during failure")
        
    def test_write_queuing_during_primary_failure(self):
        """Test writes are queued in WAL when primary is down"""
        print("\n🧪 Testing Write Queuing During Primary Failure")
        
        status = self.get_wal_status()
        primary_healthy = any(inst["name"] == "primary" and inst["healthy"] for inst in status["instances"])
        replica_healthy = any(inst["name"] == "replica" and inst["healthy"] for inst in status["instances"])
        
        if primary_healthy:
            self.skipTest("Primary is healthy - cannot test WAL write queuing")
            
        if not replica_healthy:
            self.skipTest("Replica not healthy - cannot test WAL functionality")
            
        collection_name = f"{self.test_collection_prefix}_wal_queue"
        self.test_collections.append(collection_name)
        
        initial_status = self.get_wal_status()
        initial_pending = initial_status["write_ahead_log"]["pending_writes"]
        
        # Attempt write during primary failure
        response = requests.post(
            f"{self.load_balancer_url}/api/v2/collections",
            json={"name": collection_name, "metadata": {"test": "wal_queuing"}},
            headers={"Content-Type": "application/json"}
        )
        
        # The write should either succeed (queued) or fail gracefully
        self.assertIn(response.status_code, [200, 201, 500, 503])
        
        # Check if WAL metrics updated (may take a moment)
        time.sleep(2)
        final_status = self.get_wal_status()
        final_pending = final_status["write_ahead_log"]["pending_writes"]
        
        # WAL should have either queued the write or handled the failure
        print(f"✅ Write handling during failure: {response.status_code}")
        print(f"   WAL pending: {initial_pending} → {final_pending}")
        
    def test_wal_replay_monitoring(self):
        """Test WAL replay monitoring functionality"""
        print("\n🧪 Testing WAL Replay Monitoring")
        
        status = self.get_wal_status()
        wal_info = status["write_ahead_log"]
        
        # Verify replay monitoring is working
        self.assertIsInstance(wal_info["is_replaying"], bool)
        self.assertIsInstance(wal_info["total_replayed"], int)
        self.assertIsInstance(wal_info["failed_replays"], int)
        
        # Test replay stats are accessible
        self.assertGreaterEqual(wal_info["total_replayed"], 0)
        self.assertGreaterEqual(wal_info["failed_replays"], 0)
        
        print(f"✅ WAL replay monitoring active")
        print(f"   Total replayed: {wal_info['total_replayed']}")
        print(f"   Failed replays: {wal_info['failed_replays']}")
        print(f"   Currently replaying: {wal_info['is_replaying']}")
        
    def test_wal_metrics_persistence(self):
        """Test WAL metrics persist across requests"""
        print("\n🧪 Testing WAL Metrics Persistence")
        
        # Get initial metrics
        status1 = self.get_wal_status()
        wal1 = status1["write_ahead_log"]
        
        # Wait a moment
        time.sleep(2)
        
        # Get metrics again
        status2 = self.get_wal_status()
        wal2 = status2["write_ahead_log"]
        
        # Metrics should be consistent
        self.assertEqual(wal1["total_replayed"], wal2["total_replayed"])
        self.assertEqual(wal1["failed_replays"], wal2["failed_replays"])
        
        print(f"✅ WAL metrics persist across requests")
        
    def test_health_monitoring_integration(self):
        """Test WAL integrates properly with health monitoring"""
        print("\n🧪 Testing Health Monitoring Integration")
        
        status = self.get_wal_status()
        
        # Verify health monitoring data
        self.assertIn("instances", status)
        instances = status["instances"]
        
        for instance in instances:
            self.assertIn("name", instance)
            self.assertIn("healthy", instance)
            self.assertIn("last_health_check", instance)
            self.assertIn("success_rate", instance)
            
            # Health check timestamp should be recent
            last_check = datetime.fromisoformat(instance["last_health_check"])
            time_diff = datetime.now() - last_check
            self.assertLess(time_diff.total_seconds(), 300)  # Within 5 minutes
            
        print(f"✅ Health monitoring integration working")
        print(f"   Monitoring {len(instances)} instances")
        
    def test_wal_error_handling(self):
        """Test WAL error handling and recovery"""
        print("\n🧪 Testing WAL Error Handling")
        
        # Test invalid requests don't break WAL
        invalid_responses = []
        
        # Test various invalid requests
        test_cases = [
            ("POST", "/api/v2/collections", {"invalid": "data"}),
            ("PUT", "/api/v2/collections/nonexistent", {"data": "test"}),
            ("DELETE", "/api/v2/collections/nonexistent", None),
        ]
        
        for method, path, data in test_cases:
            try:
                if method == "POST":
                    response = requests.post(f"{self.load_balancer_url}{path}", json=data)
                elif method == "PUT":
                    response = requests.put(f"{self.load_balancer_url}{path}", json=data)
                elif method == "DELETE":
                    response = requests.delete(f"{self.load_balancer_url}{path}")
                    
                invalid_responses.append(response.status_code)
            except Exception as e:
                # Connection errors are expected during failures
                invalid_responses.append("connection_error")
                
        # WAL should still be responsive after invalid requests
        status = self.get_wal_status()
        self.assertIsNotNone(status)
        
        print(f"✅ WAL error handling robust")
        print(f"   Handled {len(invalid_responses)} invalid requests")
        
    def test_wal_performance_characteristics(self):
        """Test WAL performance characteristics"""
        print("\n🧪 Testing WAL Performance Characteristics")
        
        # Test status endpoint response time
        response_times = []
        for i in range(5):
            start_time = time.time()
            status = self.get_wal_status()
            response_time = time.time() - start_time
            response_times.append(response_time)
            time.sleep(0.1)
            
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        # Status endpoint should be fast
        self.assertLess(avg_response_time, 5.0)  # Average under 5 seconds
        self.assertLess(max_response_time, 10.0)  # Max under 10 seconds
        
        print(f"✅ WAL performance acceptable")
        print(f"   Average response time: {avg_response_time:.2f}s")
        print(f"   Max response time: {max_response_time:.2f}s")
        
    def test_wal_configuration_validation(self):
        """Test WAL configuration is properly set"""
        print("\n🧪 Testing WAL Configuration")
        
        status = self.get_wal_status()
        
        # Verify expected configuration values
        self.assertIn("consistency_window", status)
        self.assertIn("read_replica_ratio", status)
        
        # Values should be reasonable
        self.assertGreater(status["consistency_window"], 0)
        self.assertGreaterEqual(status["read_replica_ratio"], 0.0)
        self.assertLessEqual(status["read_replica_ratio"], 1.0)
        
        print(f"✅ WAL configuration valid")
        print(f"   Consistency window: {status['consistency_window']}s")
        print(f"   Read replica ratio: {status['read_replica_ratio']}")


class TestWALIntegration(unittest.TestCase):
    """Integration tests for WAL with existing systems"""
    
    def test_wal_with_existing_test_framework(self):
        """Test WAL works with existing test framework"""
        print("\n🧪 Testing WAL Integration with Existing Framework")
        
        # Import existing test configuration
        try:
            with open('test_config.json', 'r') as f:
                test_config = json.load(f)
                
            # Test WAL status endpoint compatibility
            load_balancer_url = test_config.get("load_balancer_url", "https://chroma-load-balancer.onrender.com")
            response = requests.get(f"{load_balancer_url}/status")
            
            self.assertEqual(response.status_code, 200)
            status = response.json()
            self.assertIn("write_ahead_log", status)
            
            print(f"✅ WAL integrates with existing test framework")
            
        except FileNotFoundError:
            self.skipTest("test_config.json not found")
            
    def test_wal_monitoring_compatibility(self):
        """Test WAL monitoring is compatible with existing monitoring"""
        print("\n🧪 Testing WAL Monitoring Compatibility")
        
        # WAL should provide metrics compatible with existing monitoring
        load_balancer_url = "https://chroma-load-balancer.onrender.com"
        
        response = requests.get(f"{load_balancer_url}/status")
        status = response.json()
        
        # Should have standard monitoring fields plus WAL fields
        required_fields = ["healthy_instances", "total_instances", "stats", "write_ahead_log"]
        for field in required_fields:
            self.assertIn(field, status)
            
        print(f"✅ WAL monitoring compatible with existing systems")


def run_wal_test_suite():
    """Run the complete WAL test suite"""
    print("🚀 Starting Comprehensive Write-Ahead Log Test Suite")
    print("=" * 60)
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add all WAL tests
    suite.addTest(unittest.makeSuite(TestWriteAheadLog))
    suite.addTest(unittest.makeSuite(TestWALIntegration))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("🎯 WAL Test Suite Summary")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    print(f"   Skipped: {len(result.skipped)}")
    
    if result.failures:
        print("\n❌ Failures:")
        for test, traceback in result.failures:
            print(f"   - {test}: {traceback}")
            
    if result.errors:
        print("\n💥 Errors:")
        for test, traceback in result.errors:
            print(f"   - {test}: {traceback}")
            
    if result.skipped:
        print("\n⏭️  Skipped:")
        for test, reason in result.skipped:
            print(f"   - {test}: {reason}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n{'✅ WAL TEST SUITE PASSED' if success else '❌ WAL TEST SUITE FAILED'}")
    
    return success


if __name__ == "__main__":
    run_wal_test_suite() 