#!/usr/bin/env python3
"""
Master Test Runner for New Functionality - Coordinates all test suites
Tests real-time mapping, write failover, and enhanced error handling
Enhanced with bulletproof cleanup system
"""

import sys
import logging
import time
from test_base_cleanup import BulletproofTestBase
from test_real_time_mapping import RealTimeMappingTestSuite
from test_write_failover import WriteFailoverTestSuite
from test_enhanced_error_handling import EnhancedErrorHandlingTestSuite

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MasterTestCoordinator(BulletproofTestBase):
    """Master coordinator for all new functionality tests with bulletproof cleanup"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_master")
        self.test_suites = {}
        self.suite_results = {}
        
    def initialize_test_suites(self):
        """Initialize all test suites"""
        logger.info("🚀 Initializing Test Suites...")
        
        self.test_suites = {
            'real_time_mapping': RealTimeMappingTestSuite(self.base_url),
            'write_failover': WriteFailoverTestSuite(self.base_url),
            'enhanced_error_handling': EnhancedErrorHandlingTestSuite(self.base_url)
        }
        
        logger.info(f"✅ Initialized {len(self.test_suites)} test suites")
        return True
        
    def run_real_time_mapping_tests(self):
        """Run real-time mapping tests"""
        logger.info("\n🆔 Running Real-Time Mapping Tests")
        logger.info("="*50)
        
        start_time = time.time()
        suite = self.test_suites['real_time_mapping']
        
        try:
            success = suite.test_real_time_mapping()
            duration = time.time() - start_time
            
            self.suite_results['real_time_mapping'] = {
                'success': success,
                'duration': duration,
                'details': suite.get_test_summary()
            }
            
            return self.log_test_result(
                "Real-Time Mapping Suite",
                success,
                f"Mapping functionality test {'passed' if success else 'failed'}",
                duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            self.suite_results['real_time_mapping'] = {
                'success': False,
                'duration': duration,
                'details': {'error': str(e)}
            }
            
            return self.log_test_result(
                "Real-Time Mapping Suite",
                False,
                f"Exception: {str(e)}",
                duration
            )
        
    def run_write_failover_tests(self):
        """Run write failover tests"""
        logger.info("\n⚡ Running Write Failover Tests")
        logger.info("="*50)
        
        start_time = time.time()
        suite = self.test_suites['write_failover']
        
        try:
            success = suite.test_write_failover_scenario()
            duration = time.time() - start_time
            
            self.suite_results['write_failover'] = {
                'success': success,
                'duration': duration,
                'details': suite.get_test_summary()
            }
            
            return self.log_test_result(
                "Write Failover Suite",
                success,
                f"Failover functionality test {'passed' if success else 'failed'}",
                duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            self.suite_results['write_failover'] = {
                'success': False,
                'duration': duration,
                'details': {'error': str(e)}
            }
            
            return self.log_test_result(
                "Write Failover Suite",
                False,
                f"Exception: {str(e)}",
                duration
            )
            
    def run_enhanced_error_handling_tests(self):
        """Run enhanced error handling tests"""
        logger.info("\n🛡️ Running Enhanced Error Handling Tests")
        logger.info("="*50)
        
        start_time = time.time()
        suite = self.test_suites['enhanced_error_handling']
        
        try:
            # Run all error handling tests
            results = []
            results.append(suite.test_400_uuid_error_handling())
            results.append(suite.test_404_error_handling())
            results.append(suite.test_graceful_error_marking())
            
            success = all(results)
            duration = time.time() - start_time
            
            self.suite_results['enhanced_error_handling'] = {
                'success': success,
                'duration': duration,
                'details': suite.get_test_summary()
            }
            
            return self.log_test_result(
                "Enhanced Error Handling Suite",
                success,
                f"Error handling tests {'passed' if success else 'failed'} ({sum(results)}/{len(results)} tests passed)",
                duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            self.suite_results['enhanced_error_handling'] = {
                'success': False,
                'duration': duration,
                'details': {'error': str(e)}
            }
            
            return self.log_test_result(
                "Enhanced Error Handling Suite",
                False,
                f"Exception: {str(e)}",
                duration
            )
    
    def comprehensive_suite_cleanup(self):
        """Perform cleanup across all test suites"""
        logger.info("🧹 Performing Comprehensive Suite Cleanup...")
        
        total_cleanup_results = {
            'documents_deleted': 0,
            'collections_deleted': 0,
            'failed_document_cleanups': 0,
            'failed_collection_cleanups': 0
        }
        
        # Clean up each suite
        for suite_name, suite in self.test_suites.items():
            logger.info(f"  Cleaning up {suite_name} suite...")
            try:
                cleanup_results = suite.comprehensive_cleanup()
                
                # Aggregate results
                total_cleanup_results['documents_deleted'] += cleanup_results['documents_deleted']
                total_cleanup_results['collections_deleted'] += cleanup_results['collections_deleted']
                total_cleanup_results['failed_document_cleanups'] += cleanup_results['failed_document_cleanups']
                total_cleanup_results['failed_collection_cleanups'] += cleanup_results['failed_collection_cleanups']
                
            except Exception as e:
                logger.warning(f"  ⚠️ Error cleaning up {suite_name}: {e}")
        
        # Clean up master coordinator
        master_cleanup = self.comprehensive_cleanup()
        total_cleanup_results['documents_deleted'] += master_cleanup['documents_deleted']
        total_cleanup_results['collections_deleted'] += master_cleanup['collections_deleted']
        total_cleanup_results['failed_document_cleanups'] += master_cleanup['failed_document_cleanups']
        total_cleanup_results['failed_collection_cleanups'] += master_cleanup['failed_collection_cleanups']
        
        # Report comprehensive cleanup results
        logger.info(f"🧹 Master Cleanup Summary:")
        logger.info(f"   Total Documents deleted: {total_cleanup_results['documents_deleted']}")
        logger.info(f"   Total Collections deleted: {total_cleanup_results['collections_deleted']}")
        if total_cleanup_results['failed_document_cleanups'] > 0:
            logger.warning(f"   Total Failed document cleanups: {total_cleanup_results['failed_document_cleanups']}")
        if total_cleanup_results['failed_collection_cleanups'] > 0:
            logger.warning(f"   Total Failed collection cleanups: {total_cleanup_results['failed_collection_cleanups']}")
        
        return total_cleanup_results
    
    def print_master_summary(self):
        """Print comprehensive summary of all test suites"""
        logger.info("="*80)
        logger.info(f"📊 MASTER TEST SUMMARY - Session {self.test_session_id}")
        logger.info("="*80)
        
        total_success = 0
        total_tests = 0
        
        for suite_name, results in self.suite_results.items():
            logger.info(f"\n📋 {suite_name.upper().replace('_', ' ')} SUITE:")
            logger.info(f"   Status: {'✅ PASSED' if results['success'] else '❌ FAILED'}")
            logger.info(f"   Duration: {results['duration']:.2f}s")
            
            if 'details' in results and isinstance(results['details'], dict):
                if 'total' in results['details']:
                    suite_total = results['details']['total']
                    suite_passed = results['details']['passed']
                    total_tests += suite_total
                    total_success += suite_passed
                    logger.info(f"   Tests: {suite_passed}/{suite_total} passed")
                elif 'error' in results['details']:
                    logger.info(f"   Error: {results['details']['error']}")
        
        # Master coordinator summary
        master_summary = self.get_test_summary()
        if master_summary['total'] > 0:
            total_tests += master_summary['total']
            total_success += master_summary['passed']
            logger.info(f"\n📋 MASTER COORDINATOR:")
            logger.info(f"   Tests: {master_summary['passed']}/{master_summary['total']} passed")
        
        # Overall summary
        overall_success_rate = (total_success / total_tests * 100) if total_tests > 0 else 0
        logger.info(f"\n🎯 OVERALL RESULTS:")
        logger.info(f"   Total Tests: {total_tests}")
        logger.info(f"   Total Passed: {total_success}")
        logger.info(f"   Total Failed: {total_tests - total_success}")
        logger.info(f"   Success Rate: {overall_success_rate:.1f}%")
        
        logger.info("="*80)
        
        return overall_success_rate == 100.0

def main():
    """Run all new functionality tests with comprehensive cleanup"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Master Test Runner for New Functionality")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    coordinator = MasterTestCoordinator(args.url)
    
    logger.info("🚀 Starting Master Test Coordination")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info(f"🆔 Master Session ID: {coordinator.test_session_id}")
    logger.info("="*80)
    
    try:
        # Initialize all test suites
        coordinator.initialize_test_suites()
        
        # Run all test suites
        suite_results = []
        suite_results.append(coordinator.run_real_time_mapping_tests())
        
        # Add delay between test suites to prevent rate limiting
        time.sleep(5)
        suite_results.append(coordinator.run_write_failover_tests())
        
        time.sleep(5)
        suite_results.append(coordinator.run_enhanced_error_handling_tests())
        
        overall_success = all(suite_results)
        
    finally:
        # Always perform comprehensive cleanup across all suites
        coordinator.comprehensive_suite_cleanup()
    
    # Print comprehensive summary
    success = coordinator.print_master_summary()
    
    if success:
        logger.info("🎉 ALL NEW FUNCTIONALITY TESTS PASSED!")
        logger.info("🧹 Comprehensive test data isolation and cleanup completed.")
        logger.info("🚀 System ready for production with all new features operational!")
    else:
        logger.error("❌ SOME NEW FUNCTIONALITY TESTS FAILED!")
        logger.info("🧹 Test data cleanup completed to prevent pollution.")
        logger.info("🔧 Review failed tests and address issues before production deployment.")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 