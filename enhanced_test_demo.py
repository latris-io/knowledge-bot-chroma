#!/usr/bin/env python3
"""
Demo: Enhanced Test Suite with Automatic Cleanup
Shows how successful tests are automatically cleaned while failed tests preserve data
"""

import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedTestDemo:
    def __init__(self):
        self.test_data = {}  # Track data per test
        self.current_test = None
        
    def start_test(self, test_name):
        """Start tracking for a specific test"""
        self.current_test = test_name
        self.test_data[test_name] = {
            'collections': [],
            'documents': [],
            'created_items': 0
        }
        
    def create_test_data(self, data_type, count=1):
        """Simulate creating test data"""
        if self.current_test:
            self.test_data[self.current_test][data_type].extend([f"{data_type}_{i}" for i in range(count)])
            self.test_data[self.current_test]['created_items'] += count
            logger.info(f"   📝 Created {count} {data_type} for {self.current_test}")
    
    def cleanup_successful_test(self, test_name):
        """Clean up data from a successful test immediately"""
        if test_name not in self.test_data:
            return {'cleaned': 0}
            
        data = self.test_data[test_name]
        total_cleaned = data['created_items']
        
        logger.info(f"   🧹 Auto-cleanup: Removing {total_cleaned} items from successful test")
        for data_type in ['collections', 'documents']:
            if data[data_type]:
                logger.info(f"     • Deleted {len(data[data_type])} {data_type}")
        
        # Remove from tracking since cleaned
        del self.test_data[test_name]
        return {'cleaned': total_cleaned}
    
    def simulate_test_suite(self, test_name, should_pass=True):
        """Simulate running a test suite"""
        logger.info(f"\n🧪 Running {test_name} Test...")
        
        # Start tracking
        self.start_test(test_name)
        
        # Simulate creating test data
        if 'Collection' in test_name:
            self.create_test_data('collections', 2)
        if 'Document' in test_name:
            self.create_test_data('documents', 5)
        if 'WAL' in test_name:
            self.create_test_data('wal_entries', 3)
        
        # Simulate test result
        time.sleep(0.5)  # Simulate test execution time
        
        if should_pass:
            logger.info(f"✅ PASSED {test_name}")
            # AUTO-CLEANUP for successful test
            cleanup_result = self.cleanup_successful_test(test_name)
            logger.info(f"   🎯 Database kept clean: {cleanup_result['cleaned']} items removed")
            return True
        else:
            logger.info(f"❌ FAILED {test_name}")
            logger.info(f"   📋 Test data preserved for debugging")
            return False
    
    def final_cleanup(self):
        """Clean up remaining data from failed tests"""
        total_remaining = sum(data['created_items'] for data in self.test_data.values())
        if total_remaining > 0:
            logger.info(f"\n🧹 Final cleanup: {total_remaining} items from failed tests")
            for test_name, data in self.test_data.items():
                logger.info(f"   • {test_name}: {data['created_items']} items (preserved for debugging)")
        return total_remaining
    
    def run_demo(self):
        """Run demonstration of automatic cleanup"""
        logger.info("🚀 DEMO: Automatic Test Data Cleanup")
        logger.info("=" * 60)
        
        # Define test scenarios
        test_scenarios = [
            ("Health Check", True),      # Pass - auto-cleanup
            ("Collection Operations", True),  # Pass - auto-cleanup  
            ("Document Operations", False),   # Fail - preserve data
            ("WAL Functionality", True),      # Pass - auto-cleanup
            ("Load Balancer", False),         # Fail - preserve data
        ]
        
        total_auto_cleaned = 0
        
        for test_name, should_pass in test_scenarios:
            result = self.simulate_test_suite(test_name, should_pass)
            if result:
                # Count items that were auto-cleaned
                total_auto_cleaned += 2 if 'Collection' in test_name else 0
                total_auto_cleaned += 5 if 'Document' in test_name else 0
                total_auto_cleaned += 3 if 'WAL' in test_name else 0
        
        # Final cleanup
        remaining_items = self.final_cleanup()
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("📊 DEMO RESULTS")
        logger.info("="*60)
        logger.info(f"🧹 Auto-cleaned (successful tests): {total_auto_cleaned} items")
        logger.info(f"📋 Preserved (failed tests): {remaining_items} items")
        logger.info(f"🎯 Database pollution prevented: {total_auto_cleaned} unnecessary items")
        
        logger.info(f"\n💡 Benefits:")
        logger.info(f"  ✅ Clean database: Only failed test data remains")
        logger.info(f"  🐛 Debugging: Failed test data available for analysis")
        logger.info(f"  ⚡ Performance: No accumulation of test data")
        logger.info(f"  💾 Storage: Minimal database usage")

if __name__ == "__main__":
    demo = EnhancedTestDemo()
    demo.run_demo() 