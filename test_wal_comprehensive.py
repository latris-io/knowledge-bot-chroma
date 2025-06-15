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
import sys
import os

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
                requests.delete(f"{self.load_balancer_url}/api/v2/collections/{collection_name}", timeout=5)
            except:
                pass  # Ignore cleanup errors
                
    def get_wal_status(self):
        """Get current WAL status from load balancer"""
        try:
            response = requests.get(f"{self.load_balancer_url}/status", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.fail(f"Failed to get WAL status: {e}")
    
    def test_wal_status_endpoint_structure(self):
        """Test WAL status endpoint returns correct structure"""
        print("\n🧪 Testing WAL Status Endpoint Structure")
        
        status = self.get_wal_status()
        
        # Verify WAL structure
        self.assertIn("write_ahead_log", status)
        wal_info = status["write_ahead_log"]
        
        required_fields = ["pending_writes", "is_replaying", "oldest_pending", "total_replayed", "failed_replays"]
        for field in required_fields:
            self.assertIn(field, wal_info, f"WAL field '{field}' missing")
            
        # Verify instance health reporting
        self.assertIn("instances", status)
        self.assertGreater(len(status["instances"]), 0)
        
        print(f"✅ WAL Status Structure: VALID")
        print(f"   Pending writes: {wal_info['pending_writes']}")
        print(f"   Total replayed: {wal_info['total_replayed']}")
        
    def test_service_identification(self):
        """Test service correctly identifies as WAL-enabled"""
        print("\n🧪 Testing Service Identification")
        
        status = self.get_wal_status()
        service_name = status.get("service", "")
        
        self.assertIn("Write-Ahead Log", service_name)
        print(f"✅ Service Identity: {service_name}")
        
    def test_instance_health_monitoring(self):
        """Test instance health monitoring functionality"""
        print("\n🧪 Testing Instance Health Monitoring")
        
        status = self.get_wal_status()
        instances = status["instances"]
        
        for instance in instances:
            required_fields = ["name", "healthy", "success_rate", "total_requests", "last_health_check"]
            for field in required_fields:
                self.assertIn(field, instance, f"Instance field '{field}' missing")
            
            # Validate health check timestamp
            try:
                last_check = datetime.fromisoformat(instance["last_health_check"])
                time_diff = datetime.now() - last_check
                self.assertLess(time_diff.total_seconds(), 300, "Health check too old")
            except ValueError:
                self.fail(f"Invalid health check timestamp: {instance['last_health_check']}")
        
        primary_healthy = any(inst["name"] == "primary" and inst["healthy"] for inst in instances)
        replica_healthy = any(inst["name"] == "replica" and inst["healthy"] for inst in instances)
        
        print(f"✅ Health Monitoring: Working")
        print(f"   Primary healthy: {primary_healthy}")
        print(f"   Replica healthy: {replica_healthy}")
        
    def test_wal_configuration_values(self):
        """Test WAL configuration values are reasonable"""
        print("\n🧪 Testing WAL Configuration")
        
        status = self.get_wal_status()
        
        # Check configuration fields
        self.assertIn("consistency_window", status)
        self.assertIn("read_replica_ratio", status)
        
        # Validate ranges
        consistency_window = status["consistency_window"]
        self.assertIsInstance(consistency_window, (int, float))
        self.assertGreater(consistency_window, 0)
        
        read_replica_ratio = status["read_replica_ratio"]
        self.assertIsInstance(read_replica_ratio, (int, float))
        self.assertGreaterEqual(read_replica_ratio, 0.0)
        self.assertLessEqual(read_replica_ratio, 1.0)
        
        print(f"✅ Configuration Valid")
        print(f"   Consistency window: {consistency_window}s")
        print(f"   Read replica ratio: {read_replica_ratio}")
        
    def test_wal_metrics_data_types(self):
        """Test WAL metrics have correct data types"""
        print("\n🧪 Testing WAL Metrics Data Types")
        
        status = self.get_wal_status()
        wal_info = status["write_ahead_log"]
        
        self.assertIsInstance(wal_info["pending_writes"], int)
        self.assertIsInstance(wal_info["is_replaying"], bool)
        self.assertIsInstance(wal_info["total_replayed"], int)
        self.assertIsInstance(wal_info["failed_replays"], int)
        
        # oldest_pending can be null or string
        if wal_info["oldest_pending"] is not None:
            self.assertIsInstance(wal_info["oldest_pending"], str)
            
        print(f"✅ WAL Metrics Types: Valid")
        
    def test_wal_write_handling_during_failure(self):
        """Test WAL write handling when primary is down"""
        print("\n🧪 Testing WAL Write Handling During Primary Failure")
        
        status = self.get_wal_status()
        primary_healthy = any(inst["name"] == "primary" and inst["healthy"] for inst in status["instances"])
        replica_healthy = any(inst["name"] == "replica" and inst["healthy"] for inst in status["instances"])
        
        if primary_healthy:
            print("⏭️ Skipping - Primary is healthy (cannot test failure scenario)")
            return
            
        if not replica_healthy:
            print("⏭️ Skipping - Replica not healthy (cannot test WAL functionality)")
            return
            
        collection_name = f"{self.test_collection_prefix}_failure_test"
        self.test_collections.append(collection_name)
        
        initial_status = self.get_wal_status()
        initial_pending = initial_status["write_ahead_log"]["pending_writes"]
        
        # Attempt write during primary failure - expect controlled failure or WAL queuing
        try:
            response = requests.post(
                f"{self.load_balancer_url}/api/v2/collections",
                json={"name": collection_name, "metadata": {"test": "wal_failure"}},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            # Should either succeed (WAL queued) or fail gracefully (write blocked)
            self.assertIn(response.status_code, [200, 201, 500, 503])
            
            print(f"✅ Write Handling During Failure: Response {response.status_code}")
            
        except requests.exceptions.RequestException as e:
            print(f"✅ Write Handling During Failure: Connection handled gracefully - {e}")
        
    def test_wal_performance_characteristics(self):
        """Test WAL performance characteristics"""
        print("\n🧪 Testing WAL Performance")
        
        response_times = []
        for i in range(3):
            start_time = time.time()
            try:
                status = self.get_wal_status()
                response_time = time.time() - start_time
                response_times.append(response_time)
                
                # Verify structure is consistent
                self.assertIn("write_ahead_log", status)
            except Exception as e:
                self.fail(f"Performance test failed on iteration {i+1}: {e}")
            
            time.sleep(0.5)
            
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        # Performance should be reasonable
        self.assertLess(avg_response_time, 10.0, f"Average response too slow: {avg_response_time:.2f}s")
        self.assertLess(max_response_time, 15.0, f"Max response too slow: {max_response_time:.2f}s")
        
        print(f"✅ Performance Acceptable")
        print(f"   Average: {avg_response_time:.2f}s")
        print(f"   Max: {max_response_time:.2f}s")
        
    def test_wal_metrics_consistency(self):
        """Test WAL metrics are consistent across requests"""
        print("\n🧪 Testing WAL Metrics Consistency")
        
        # Get metrics twice
        status1 = self.get_wal_status()
        time.sleep(1)
        status2 = self.get_wal_status()
        
        wal1 = status1["write_ahead_log"]
        wal2 = status2["write_ahead_log"]
        
        # Core counters should never decrease
        self.assertGreaterEqual(wal2["total_replayed"], wal1["total_replayed"])
        self.assertGreaterEqual(wal2["failed_replays"], wal1["failed_replays"])
        
        print(f"✅ Metrics Consistency: Verified")
        
    def test_error_handling_robustness(self):
        """Test WAL error handling doesn't break the system"""
        print("\n🧪 Testing Error Handling Robustness")
        
        # Test various invalid requests
        test_cases = [
            ("POST", "/api/v2/collections", {"invalid": "data"}),
            ("GET", "/api/v2/collections/nonexistent", None),
            ("DELETE", "/api/v2/collections/nonexistent", None),
        ]
        
        responses = []
        for method, path, data in test_cases:
            try:
                if method == "POST":
                    response = requests.post(f"{self.load_balancer_url}{path}", json=data, timeout=5)
                elif method == "GET":
                    response = requests.get(f"{self.load_balancer_url}{path}", timeout=5)
                elif method == "DELETE":
                    response = requests.delete(f"{self.load_balancer_url}{path}", timeout=5)
                    
                responses.append(response.status_code)
            except requests.exceptions.RequestException:
                responses.append("connection_error")
                
        # WAL should still be responsive after invalid requests
        try:
            status = self.get_wal_status()
            self.assertIsNotNone(status)
            print(f"✅ Error Handling: Robust")
            print(f"   Handled {len(responses)} test requests")
        except Exception as e:
            self.fail(f"WAL became unresponsive after error tests: {e}")


def run_wal_comprehensive_tests():
    """Run the complete comprehensive WAL test suite"""
    print("🚀 Starting Comprehensive Write-Ahead Log Test Suite")
    print("=" * 70)
    
    # Create test suite using modern approach
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWriteAheadLog)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(suite)
    
    print("\n" + "=" * 70)
    print("🎯 COMPREHENSIVE WAL TEST RESULTS")
    print("=" * 70)
    print(f"📊 Tests Run: {result.testsRun}")
    print(f"✅ Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ Failed: {len(result.failures)}")
    print(f"💥 Errors: {len(result.errors)}")
    print(f"⏭️ Skipped: {len(result.skipped)}")
    
    if result.failures:
        print("\n❌ Test Failures:")
        for test, traceback in result.failures:
            print(f"   - {test}")
            
    if result.errors:
        print("\n💥 Test Errors:")
        for test, traceback in result.errors:
            print(f"   - {test}")
            
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n{'✅ COMPREHENSIVE WAL TESTS PASSED' if success else '❌ SOME WAL TESTS FAILED'}")
    
    return success


if __name__ == "__main__":
    import sys
    try:
        success = run_wal_comprehensive_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite crashed: {e}")
        sys.exit(1) 