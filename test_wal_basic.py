#!/usr/bin/env python3
"""
Basic Write-Ahead Log Test Suite
Tests core WAL functionality for integration with existing test framework
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_load_balancer_url():
    """Get load balancer URL from environment"""
    return os.getenv("LOAD_BALANCER_URL", "https://chroma-load-balancer.onrender.com")

def get_wal_status():
    """Get current WAL status"""
    try:
        url = get_load_balancer_url()
        response = requests.get(f"{url}/status", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"❌ Failed to get WAL status: {e}")
        raise

def test_wal_status_endpoint():
    """Test WAL status endpoint availability and structure"""
    logger.info("🧪 Testing WAL Status Endpoint")
    
    try:
        status = get_wal_status()
        
        # Check for WAL structure
        assert "write_ahead_log" in status, "WAL section missing from status"
        wal_info = status["write_ahead_log"]
        
        # Check required fields
        required_fields = ["pending_writes", "is_replaying", "oldest_pending", "total_replayed", "failed_replays"]
        for field in required_fields:
            assert field in wal_info, f"WAL field '{field}' missing"
            
        # Check data types
        assert isinstance(wal_info["pending_writes"], int), "pending_writes should be integer"
        assert isinstance(wal_info["is_replaying"], bool), "is_replaying should be boolean"
        assert isinstance(wal_info["total_replayed"], int), "total_replayed should be integer"
        assert isinstance(wal_info["failed_replays"], int), "failed_replays should be integer"
        
        logger.info(f"✅ WAL Status Endpoint: PASSED")
        logger.info(f"   Pending writes: {wal_info['pending_writes']}")
        logger.info(f"   Total replayed: {wal_info['total_replayed']}")
        logger.info(f"   Failed replays: {wal_info['failed_replays']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ WAL Status Endpoint: FAILED - {e}")
        return False

def test_instance_health_monitoring():
    """Test that instance health monitoring is working"""
    logger.info("🧪 Testing Instance Health Monitoring")
    
    try:
        status = get_wal_status()
        
        # Check instances structure
        assert "instances" in status, "Instances section missing"
        instances = status["instances"]
        assert len(instances) > 0, "No instances found"
        
        # Check instance structure
        for instance in instances:
            required_fields = ["name", "healthy", "success_rate", "total_requests", "last_health_check"]
            for field in required_fields:
                assert field in instance, f"Instance field '{field}' missing"
            
            # Validate health check timestamp
            try:
                datetime.fromisoformat(instance["last_health_check"])
            except ValueError:
                raise AssertionError(f"Invalid health check timestamp: {instance['last_health_check']}")
        
        # Count healthy vs unhealthy
        primary_healthy = any(inst["name"] == "primary" and inst["healthy"] for inst in instances)
        replica_healthy = any(inst["name"] == "replica" and inst["healthy"] for inst in instances)
        
        logger.info(f"✅ Instance Health Monitoring: PASSED")
        logger.info(f"   Primary healthy: {primary_healthy}")
        logger.info(f"   Replica healthy: {replica_healthy}")
        logger.info(f"   Total instances: {len(instances)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Instance Health Monitoring: FAILED - {e}")
        return False

def test_wal_configuration():
    """Test WAL configuration values are reasonable"""
    logger.info("🧪 Testing WAL Configuration")
    
    try:
        status = get_wal_status()
        
        # Check configuration fields
        assert "consistency_window" in status, "consistency_window missing"
        assert "read_replica_ratio" in status, "read_replica_ratio missing"
        
        # Validate ranges
        consistency_window = status["consistency_window"]
        assert isinstance(consistency_window, (int, float)), "consistency_window should be numeric"
        assert consistency_window > 0, "consistency_window should be positive"
        
        read_replica_ratio = status["read_replica_ratio"]
        assert isinstance(read_replica_ratio, (int, float)), "read_replica_ratio should be numeric"
        assert 0.0 <= read_replica_ratio <= 1.0, "read_replica_ratio should be between 0 and 1"
        
        logger.info(f"✅ WAL Configuration: PASSED")
        logger.info(f"   Consistency window: {consistency_window}s")
        logger.info(f"   Read replica ratio: {read_replica_ratio}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ WAL Configuration: FAILED - {e}")
        return False

def test_wal_performance():
    """Test WAL status endpoint performance"""
    logger.info("🧪 Testing WAL Performance")
    
    try:
        # Test multiple requests to check consistency and speed
        response_times = []
        
        for i in range(3):
            start_time = time.time()
            status = get_wal_status()
            response_time = time.time() - start_time
            response_times.append(response_time)
            
            # Basic sanity check
            assert "write_ahead_log" in status, f"WAL missing in request {i+1}"
            
            time.sleep(0.5)  # Brief pause between requests
        
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        # Performance assertions
        assert avg_response_time < 10.0, f"Average response time too slow: {avg_response_time:.2f}s"
        assert max_response_time < 15.0, f"Max response time too slow: {max_response_time:.2f}s"
        
        logger.info(f"✅ WAL Performance: PASSED")
        logger.info(f"   Average response time: {avg_response_time:.2f}s")
        logger.info(f"   Max response time: {max_response_time:.2f}s")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ WAL Performance: FAILED - {e}")
        return False

def test_service_identification():
    """Test that the service correctly identifies itself as WAL-enabled"""
    logger.info("🧪 Testing Service Identification")
    
    try:
        status = get_wal_status()
        
        # Check service identification
        service_name = status.get("service", "")
        assert "Write-Ahead Log" in service_name, f"Service doesn't identify as WAL-enabled: {service_name}"
        
        logger.info(f"✅ Service Identification: PASSED")
        logger.info(f"   Service: {service_name}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Service Identification: FAILED - {e}")
        return False

def test_wal_metrics_persistence():
    """Test that WAL metrics persist across requests"""
    logger.info("🧪 Testing WAL Metrics Persistence")
    
    try:
        # Get initial metrics
        status1 = get_wal_status()
        wal1 = status1["write_ahead_log"]
        
        time.sleep(2)  # Wait a moment
        
        # Get metrics again
        status2 = get_wal_status()
        wal2 = status2["write_ahead_log"]
        
        # Core metrics should be consistent (they may increase but not decrease)
        assert wal2["total_replayed"] >= wal1["total_replayed"], "total_replayed decreased"
        assert wal2["failed_replays"] >= wal1["failed_replays"], "failed_replays decreased"
        
        logger.info(f"✅ WAL Metrics Persistence: PASSED")
        logger.info(f"   Metrics stable between requests")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ WAL Metrics Persistence: FAILED - {e}")
        return False

def run_all_wal_tests():
    """Run all WAL tests"""
    logger.info("🚀 Starting Basic Write-Ahead Log Test Suite")
    logger.info(f"📡 Load Balancer URL: {get_load_balancer_url()}")
    logger.info("=" * 60)
    
    tests = [
        ("WAL Status Endpoint", test_wal_status_endpoint),
        ("Instance Health Monitoring", test_instance_health_monitoring),
        ("WAL Configuration", test_wal_configuration),
        ("WAL Performance", test_wal_performance),
        ("Service Identification", test_service_identification),
        ("WAL Metrics Persistence", test_wal_metrics_persistence),
    ]
    
    results = []
    start_time = time.time()
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            logger.error(f"💥 {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    total_duration = time.time() - start_time
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    logger.info("\n" + "=" * 60)
    logger.info("🎯 BASIC WAL TEST SUITE RESULTS")
    logger.info("=" * 60)
    logger.info(f"📊 Tests Run: {total}")
    logger.info(f"✅ Passed: {passed}")
    logger.info(f"❌ Failed: {total - passed}")
    logger.info(f"📈 Success Rate: {passed/total*100:.1f}%")
    logger.info(f"⏱️ Duration: {total_duration:.1f}s")
    
    # Individual results
    logger.info(f"\n📋 Individual Results:")
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"  {status} - {test_name}")
    
    if passed == total:
        logger.info(f"\n🎉 All WAL tests passed! Write-Ahead Log is functioning correctly.")
        return True
    else:
        logger.info(f"\n⚠️ Some WAL tests failed. Review the errors above.")
        return False

def main():
    """Main entry point"""
    try:
        success = run_all_wal_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n🛑 Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n💥 Test suite crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 