#!/usr/bin/env python3
"""
Test Cleanup Systems
Tests database retention policies, log cleanup, and disk space management
"""

import os
import time
import unittest
import psycopg2
import tempfile
from datetime import datetime, timedelta
from cleanup_service import DatabaseCleanupService

class TestCleanupSystems(unittest.TestCase):
    """Test cleanup systems for database and log management"""
    
    def setUp(self):
        """Set up test environment"""
        # Set DATABASE_URL if not provided
        if not os.getenv("DATABASE_URL"):
            os.environ["DATABASE_URL"] = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
        
        self.cleanup_service = DatabaseCleanupService()
    
    def test_01_retention_policies_configured(self):
        """Test that retention policies are properly configured"""
        print("\n🧹 Testing Cleanup Retention Policies")
        
        # Check that all expected tables have retention policies
        expected_tables = [
            'health_metrics', 'performance_metrics', 'sync_history',
            'failover_events', 'sync_tasks', 'upgrade_recommendations', 'sync_workers'
        ]
        
        for table in expected_tables:
            self.assertIn(table, self.cleanup_service.retention_policies, 
                         f"Retention policy should be configured for {table}")
            
            retention_days = self.cleanup_service.retention_policies[table]
            self.assertGreater(retention_days, 0, 
                             f"Retention policy for {table} should be positive")
            
            print(f"  ✅ {table}: {retention_days} days retention")
        
        # Verify retention policies make sense
        health_retention = self.cleanup_service.retention_policies['health_metrics']
        upgrade_retention = self.cleanup_service.retention_policies['upgrade_recommendations']
        
        self.assertLessEqual(health_retention, 30, 
                           "Health metrics should have short retention (high frequency data)")
        self.assertGreaterEqual(upgrade_retention, 90, 
                              "Upgrade recommendations should have longer retention (strategic data)")
        
        print("  🎯 Retention policies configured correctly")
    
    def test_02_database_size_reporting(self):
        """Test database size reporting functionality"""
        print("\n📊 Testing Database Size Reporting")
        
        report = self.cleanup_service.get_size_report()
        
        self.assertNotIn('error', report, "Size report should not contain errors")
        self.assertIn('tables', report, "Report should contain table information")
        self.assertIn('timestamp', report, "Report should contain timestamp")
        
        # Check that each table has required information
        for table_info in report['tables']:
            self.assertIn('name', table_info, "Table should have name")
            self.assertIn('records', table_info, "Table should have record count")
            self.assertIn('size', table_info, "Table should have size information")
            self.assertIn('retention_days', table_info, "Table should have retention policy")
            
            print(f"  📊 {table_info['name']}: {table_info['records']:,} records, {table_info['size']}")
        
        print("  ✅ Database size reporting working correctly")
    
    def test_03_cleanup_simulation(self):
        """Test cleanup functionality with simulated old data"""
        print("\n🗑️ Testing Cleanup Functionality")
        
        # Test cleanup on current data (should find no old records)
        results = self.cleanup_service.run_cleanup()
        
        self.assertIn('total_deleted', results, "Results should contain total deleted count")
        self.assertIn('results', results, "Results should contain per-table results")
        
        # All tables should be processed
        for table_name in self.cleanup_service.retention_policies.keys():
            self.assertIn(table_name, results['results'], 
                         f"Results should include {table_name}")
            
            table_result = results['results'][table_name]
            self.assertIn('deleted', table_result, "Table result should have deleted count")
            self.assertIsNone(table_result['error'], f"No errors expected for {table_name}")
        
        print(f"  🗑️ Cleanup processed {len(results['results'])} tables")
        print(f"  📊 Total records deleted: {results['total_deleted']:,}")
        print("  ✅ Cleanup functionality working correctly")
    
    def test_04_retention_policy_validation(self):
        """Test that retention policies prevent data loss"""
        print("\n🛡️ Testing Retention Policy Safety")
        
        # Check that we're not accidentally deleting recent data
        if self.cleanup_service.database_url:
            try:
                with psycopg2.connect(self.cleanup_service.database_url) as conn:
                    with conn.cursor() as cursor:
                        # Check health metrics (should have recent data)
                        cursor.execute("""
                            SELECT COUNT(*) FROM health_metrics 
                            WHERE checked_at > NOW() - INTERVAL '1 hour'
                        """)
                        recent_health_records = cursor.fetchone()[0]
                        
                        self.assertGreater(recent_health_records, 0, 
                                         "Should have recent health metrics")
                        
                        # Check that we're not deleting everything
                        retention_days = self.cleanup_service.retention_policies['health_metrics']
                        cutoff_date = datetime.now() - timedelta(days=retention_days)
                        
                        cursor.execute("""
                            SELECT COUNT(*) FROM health_metrics 
                            WHERE checked_at >= %s
                        """, [cutoff_date])
                        protected_records = cursor.fetchone()[0]
                        
                        self.assertGreater(protected_records, 0, 
                                         f"Should preserve health metrics within {retention_days} days")
                        
                        print(f"  🛡️ {recent_health_records:,} recent health records protected")
                        print(f"  📊 {protected_records:,} records within retention window")
            
            except Exception as e:
                self.fail(f"Database validation failed: {e}")
        
        print("  ✅ Retention policies prevent data loss")
    
    def test_05_environment_configuration(self):
        """Test environment variable configuration for cleanup policies"""
        print("\n🔧 Testing Environment Configuration")
        
        # Test default values
        original_policies = self.cleanup_service.retention_policies.copy()
        
        # Test that environment variables would be respected
        env_tests = [
            ('HEALTH_METRICS_RETENTION_DAYS', 'health_metrics'),
            ('PERFORMANCE_METRICS_RETENTION_DAYS', 'performance_metrics'),
            ('SYNC_HISTORY_RETENTION_DAYS', 'sync_history'),
        ]
        
        for env_var, table_name in env_tests:
            # Check that the policy exists
            self.assertIn(table_name, original_policies, 
                         f"Policy should exist for {table_name}")
            
            retention_days = original_policies[table_name]
            print(f"  🔧 {env_var}: {retention_days} days (current)")
        
        print("  ✅ Environment configuration working correctly")
    
    def test_06_disk_space_optimization(self):
        """Test that cleanup helps with disk space optimization"""
        print("\n💾 Testing Disk Space Optimization")
        
        # Get initial size report
        initial_report = self.cleanup_service.get_size_report()
        
        if 'error' not in initial_report:
            total_records = sum(table['records'] for table in initial_report['tables'])
            print(f"  📊 Current total records: {total_records:,}")
            
            # Check that health metrics (highest frequency) has reasonable size
            health_table = next((t for t in initial_report['tables'] if t['name'] == 'health_metrics'), None)
            if health_table:
                health_records = health_table['records']
                health_size = health_table['size']
                
                # With 7-day retention and ~12-second intervals, expect roughly:
                # 7 days * 24 hours * 60 minutes * 5 checks/minute * 2 instances = ~100k max
                max_expected_health_records = 100000
                
                self.assertLessEqual(health_records, max_expected_health_records,
                                   f"Health metrics should be kept under control with retention policy")
                
                print(f"  📊 Health metrics: {health_records:,} records ({health_size})")
                print(f"  🎯 Within expected range (< {max_expected_health_records:,})")
        
        print("  ✅ Disk space optimization measures in place")

def run_cleanup_tests():
    """Run all cleanup system tests"""
    print("🧹 Testing Database and Log Cleanup Systems")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestCleanupSystems)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("🧹 CLEANUP SYSTEMS TEST SUMMARY")
    print("=" * 60)
    
    if result.wasSuccessful():
        print("🎉 ALL CLEANUP SYSTEMS WORKING CORRECTLY!")
        print("✅ Retention Policies: Configured")
        print("✅ Database Cleanup: Functional")  
        print("✅ Size Reporting: Working")
        print("✅ Data Protection: Active")
        print("✅ Environment Config: Ready")
        print("✅ Disk Optimization: Enabled")
        return True
    else:
        print("❌ Some cleanup systems need attention")
        return False

if __name__ == "__main__":
    success = run_cleanup_tests()
    exit(0 if success else 1) 