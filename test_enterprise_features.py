#!/usr/bin/env python3
"""
Comprehensive Enterprise Features Test Suite
Tests all production-grade features: monitoring, failover, sync, notifications, PostgreSQL coordination
"""

import os
import time
import json
import psycopg2
import requests
import unittest
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha")
LOAD_BALANCER_URL = "https://chroma-load-balancer.onrender.com"
PRIMARY_URL = "https://chroma-primary.onrender.com" 
REPLICA_URL = "https://chroma-replica.onrender.com"

class TestEnterpriseFeatures(unittest.TestCase):
    """Comprehensive test suite for all enterprise features"""
    
    def setUp(self):
        """Set up test environment"""
        if not DATABASE_URL:
            self.skipTest("DATABASE_URL not available")
            
    def test_01_health_monitoring_system(self):
        """Test health monitoring system and PostgreSQL tracking"""
        print("\n🏥 Testing Health Monitoring System")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                # Check that health monitoring is active
                cursor.execute("""
                    SELECT COUNT(*) FROM health_metrics 
                    WHERE checked_at > NOW() - INTERVAL '5 minutes'
                """)
                recent_checks = cursor.fetchone()[0]
                self.assertGreater(recent_checks, 0, "Health monitoring should be active")
                
                # Check both instances are being monitored
                cursor.execute("""
                    SELECT DISTINCT instance_name FROM health_metrics 
                    WHERE checked_at > NOW() - INTERVAL '1 hour'
                    ORDER BY instance_name
                """)
                monitored_instances = [row[0] for row in cursor.fetchall()]
                expected_instances = {'primary', 'replica'}
                actual_instances = set(monitored_instances)
                self.assertEqual(actual_instances, expected_instances, 
                               f"Should monitor both instances. Expected: {expected_instances}, Got: {actual_instances}")
                
                print("  ✅ Health monitoring system working correctly")
    
    def test_02_load_balancer_coordination(self):
        """Test load balancer coordination and routing logic"""
        print("\n⚖️ Testing Load Balancer Coordination")
        
        # Test load balancer health endpoint
        response = requests.get(f"{LOAD_BALANCER_URL}/health")
        self.assertEqual(response.status_code, 200, "Load balancer health check should work")
        
        health_data = response.json()
        self.assertEqual(health_data['status'], 'healthy', "Load balancer should report healthy")
        
        # Test load balancer status endpoint
        response = requests.get(f"{LOAD_BALANCER_URL}/status")
        self.assertEqual(response.status_code, 200, "Load balancer status should work")
        
        status_data = response.json()
        self.assertEqual(status_data['healthy_instances'], 2, "Should have 2 healthy instances")
        self.assertEqual(status_data['total_instances'], 2, "Should track 2 total instances")
        
        print("  ✅ Load balancer coordination working correctly")
    
    def test_03_failover_event_logging(self):
        """Test failover event logging system"""
        print("\n🚨 Testing Failover Event Logging")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                # Check failover events table structure
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'failover_events' 
                    ORDER BY ordinal_position
                """)
                columns = [row[0] for row in cursor.fetchall()]
                expected_columns = ['id', 'event_type', 'from_instance', 'to_instance', 'reason', 'success', 'occurred_at']
                
                for col in expected_columns:
                    self.assertIn(col, columns, f"failover_events table should have {col} column")
                
                print("  ✅ Failover event logging system ready")
    
    def test_04_sync_history_tracking(self):
        """Test sync history tracking system"""
        print("\n🔄 Testing Sync History Tracking")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                # Check sync_history table structure
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'sync_history' 
                    ORDER BY ordinal_position
                """)
                columns = [row[0] for row in cursor.fetchall()]
                expected_columns = ['id', 'collection_id', 'sync_started_at', 'sync_completed_at', 
                                  'documents_processed', 'sync_duration_seconds', 'success', 'error_message']
                
                for col in expected_columns:
                    self.assertIn(col, columns, f"sync_history table should have {col} column")
                
                print("  ✅ Sync history tracking system ready")
    
    def test_05_daily_metrics_aggregation(self):
        """Test daily metrics aggregation system"""
        print("\n📊 Testing Daily Metrics Aggregation")
        
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                # Check sync_metrics_daily table structure
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'sync_metrics_daily' 
                    ORDER BY ordinal_position
                """)
                columns = [row[0] for row in cursor.fetchall()]
                expected_columns = ['metric_date', 'total_collections_synced', 'total_documents_synced', 
                                  'total_sync_time_seconds', 'average_lag_seconds', 'error_count', 'created_at']
                
                for col in expected_columns:
                    self.assertIn(col, columns, f"sync_metrics_daily table should have {col} column")
                
                print("  ✅ Daily metrics aggregation system ready")
    
    def test_06_full_system_integration(self):
        """Test full system integration - all components working together"""
        print("\n🌐 Testing Full System Integration")
        
        # Test the complete request flow
        test_results = {
            'load_balancer_healthy': False,
            'primary_accessible': False,
            'replica_accessible': False,
            'database_coordinated': False,
            'monitoring_active': False
        }
        
        # 1. Test load balancer
        try:
            response = requests.get(f"{LOAD_BALANCER_URL}/health", timeout=10)
            test_results['load_balancer_healthy'] = response.status_code == 200
        except:
            pass
        
        # 2. Test direct primary access
        try:
            response = requests.get(f"{PRIMARY_URL}/api/v2/version", timeout=10)
            test_results['primary_accessible'] = response.status_code == 200
        except:
            pass
        
        # 3. Test direct replica access
        try:
            response = requests.get(f"{REPLICA_URL}/api/v2/version", timeout=10)
            test_results['replica_accessible'] = response.status_code == 200
        except:
            pass
        
        # 4. Test database coordination
        try:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    test_results['database_coordinated'] = True
        except:
            pass
        
        # 5. Test monitoring is active
        try:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) FROM health_metrics 
                        WHERE checked_at > NOW() - INTERVAL '5 minutes'
                    """)
                    recent_checks = cursor.fetchone()[0]
                    test_results['monitoring_active'] = recent_checks > 0
        except:
            pass
        
        # Report results
        for component, status in test_results.items():
            status_icon = "✅" if status else "❌"
            print(f"  {status_icon} {component.replace('_', ' ').title()}: {status}")
            self.assertTrue(status, f"{component} should be working in full system integration")
        
        # Calculate overall system health
        healthy_components = sum(test_results.values())
        total_components = len(test_results)
        system_health = (healthy_components / total_components) * 100
        
        print(f"  🎯 Overall System Health: {system_health:.1f}% ({healthy_components}/{total_components})")
        self.assertEqual(system_health, 100.0, "Full system should be 100% healthy")
        
        print("  ✅ Full system integration working perfectly")

def run_enterprise_tests():
    """Run all enterprise feature tests"""
    print("🏢 Running Comprehensive Enterprise Features Test Suite")
    print("=" * 80)
    print("Testing: Health Monitoring, Failover, Sync, PostgreSQL Coordination")
    print()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestEnterpriseFeatures)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout, buffer=False)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 80)
    print("🏢 ENTERPRISE FEATURES TEST SUMMARY")
    print("=" * 80)
    
    if result.wasSuccessful():
        print("🎉 ALL ENTERPRISE FEATURES WORKING CORRECTLY!")
        print("✅ Health Monitoring: ACTIVE")
        print("✅ Load Balancer: OPERATIONAL") 
        print("✅ Failover Logging: READY")
        print("✅ Sync Tracking: FUNCTIONAL")
        print("✅ PostgreSQL Coordination: WORKING")
        print("✅ System Integration: COMPLETE")
        return True
    else:
        print("❌ SOME ENTERPRISE FEATURES NEED ATTENTION")
        print(f"   Failed: {len(result.failures)} tests")
        print(f"   Errors: {len(result.errors)} tests")
        
        for test, error in result.failures + result.errors:
            print(f"   ❌ {test}: {error.split('AssertionError:')[-1].strip()}")
        return False

if __name__ == "__main__":
    success = run_enterprise_tests()
    sys.exit(0 if success else 1) 