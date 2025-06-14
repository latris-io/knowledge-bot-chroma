#!/usr/bin/env python3
"""
Comprehensive Test Runner for ChromaDB Infrastructure
Runs all test suites: basic, advanced, distributed, monitoring, production
"""

import os
import sys
import time
import logging
import subprocess
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChromaDBTestRunner:
    """Comprehensive test runner for all ChromaDB test suites"""
    
    def __init__(self):
        self.test_suites = [
            {
                'name': 'Basic Functionality',
                'script': 'test_suite.py',
                'description': 'Core connectivity, operations, load balancing',
                'required': True
            },
            {
                'name': 'Advanced Performance',
                'script': 'advanced_tests.py',
                'description': 'Performance testing, concurrent users',
                'required': False
            },
            {
                'name': 'Distributed Sync',
                'script': 'test_distributed_sync.py',
                'description': 'Coordinator/worker coordination, task distribution',
                'required': False
            },
            {
                'name': 'Monitoring & Slack',
                'script': 'test_monitoring_and_slack.py',
                'description': 'Resource monitoring, upgrade alerts, Slack notifications',
                'required': False
            },
            {
                'name': 'Production Features',
                'script': 'test_production_features.py',
                'description': 'Memory optimization, backward compatibility',
                'required': True
            },
            {
                'name': 'Load Balancer Logic',
                'script': 'test_load_balancer_logic.py',
                'description': 'Load balancer specific functionality',
                'required': False
            }
        ]
        
        self.results = []
        self.start_time = None
    
    def check_prerequisites(self):
        """Check that all required test files exist"""
        logger.info("🔍 Checking test prerequisites...")
        
        missing_files = []
        for suite in self.test_suites:
            if not os.path.exists(suite['script']):
                missing_files.append(suite['script'])
        
        if missing_files:
            logger.error(f"❌ Missing test files: {missing_files}")
            return False
        
        # Check environment variables
        required_env_vars = ['DATABASE_URL']
        missing_env = []
        for var in required_env_vars:
            if not os.getenv(var):
                missing_env.append(var)
        
        if missing_env:
            logger.warning(f"⚠️ Missing environment variables: {missing_env}")
            logger.warning("Some tests may be skipped")
        
        logger.info("✅ Prerequisites check complete")
        return True
    
    def run_test_suite(self, suite_info: dict) -> dict:
        """Run a single test suite"""
        suite_name = suite_info['name']
        script = suite_info['script']
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 Running {suite_name} Tests")
        logger.info(f"📄 Script: {script}")
        logger.info(f"📝 Description: {suite_info['description']}")
        logger.info(f"{'='*60}")
        
        start_time = time.time()
        
        try:
            # Run the test script
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per test suite
            )
            
            duration = time.time() - start_time
            success = result.returncode == 0
            
            test_result = {
                'name': suite_name,
                'script': script,
                'success': success,
                'duration': duration,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode
            }
            
            if success:
                logger.info(f"✅ {suite_name} tests PASSED ({duration:.1f}s)")
            else:
                logger.error(f"❌ {suite_name} tests FAILED ({duration:.1f}s)")
                logger.error(f"Error output: {result.stderr[:200]}...")
            
            return test_result
            
        except subprocess.TimeoutExpired:
            logger.error(f"⏰ {suite_name} tests TIMED OUT (5 minutes)")
            return {
                'name': suite_name,
                'script': script,
                'success': False,
                'duration': 300,
                'stdout': '',
                'stderr': 'Test suite timed out after 5 minutes',
                'return_code': -1
            }
        except Exception as e:
            logger.error(f"💥 {suite_name} tests CRASHED: {e}")
            return {
                'name': suite_name,
                'script': script,
                'success': False,
                'duration': time.time() - start_time,
                'stdout': '',
                'stderr': f'Test suite crashed: {str(e)}',
                'return_code': -2
            }
    
    def run_all_tests(self, include_optional: bool = True):
        """Run all test suites"""
        logger.info("🚀 Starting Comprehensive ChromaDB Test Suite")
        logger.info(f"📅 Started at: {datetime.now().isoformat()}")
        logger.info(f"🔧 Include optional tests: {include_optional}")
        
        self.start_time = time.time()
        
        if not self.check_prerequisites():
            logger.error("❌ Prerequisites check failed - aborting tests")
            return False
        
        # Run each test suite
        for suite_info in self.test_suites:
            if not include_optional and not suite_info['required']:
                logger.info(f"⏭️ Skipping optional test: {suite_info['name']}")
                continue
            
            result = self.run_test_suite(suite_info)
            self.results.append(result)
        
        # Generate final report
        return self.generate_final_report()
    
    def generate_final_report(self):
        """Generate comprehensive test report"""
        total_duration = time.time() - self.start_time
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        
        logger.info("\n" + "="*80)
        logger.info("🏁 COMPREHENSIVE TEST SUITE RESULTS")
        logger.info("="*80)
        logger.info(f"📊 Total Test Suites: {total_tests}")
        logger.info(f"✅ Passed: {passed_tests}")
        logger.info(f"❌ Failed: {failed_tests}")
        logger.info(f"📈 Success Rate: {passed_tests/total_tests*100:.1f}%")
        logger.info(f"⏱️ Total Duration: {total_duration:.1f}s")
        
        # Detailed results
        logger.info(f"\n📋 Detailed Results:")
        for result in self.results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            logger.info(f"  {status} - {result['name']} ({result['duration']:.1f}s)")
        
        # Failed test details
        if failed_tests > 0:
            logger.info(f"\n❌ Failed Test Details:")
            for result in self.results:
                if not result['success']:
                    logger.info(f"\n  {result['name']}:")
                    logger.info(f"    Script: {result['script']}")
                    logger.info(f"    Return Code: {result['return_code']}")
                    logger.info(f"    Error: {result['stderr'][:100]}...")
        
        # Recommendations
        logger.info(f"\n💡 Recommendations:")
        if passed_tests == total_tests:
            logger.info("  🎉 All tests passed! Your ChromaDB infrastructure is ready for production.")
        elif passed_tests >= total_tests * 0.8:
            logger.info("  ⚠️ Most tests passed. Review failed tests and fix critical issues.")
        else:
            logger.info("  🚨 Many tests failed. Review infrastructure setup and configuration.")
        
        return passed_tests == total_tests
    
    def save_report(self, filename: str = None):
        """Save detailed test report to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.json"
        
        import json
        
        report_data = {
            'test_run': {
                'timestamp': datetime.now().isoformat(),
                'total_duration': time.time() - self.start_time if self.start_time else 0,
                'total_suites': len(self.results),
                'passed_suites': sum(1 for r in self.results if r['success']),
                'failed_suites': sum(1 for r in self.results if not r['success'])
            },
            'suite_results': self.results
        }
        
        try:
            with open(filename, 'w') as f:
                json.dump(report_data, f, indent=2)
            logger.info(f"📄 Detailed test report saved to: {filename}")
        except Exception as e:
            logger.error(f"❌ Failed to save report: {e}")

def main():
    """Main test runner function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ChromaDB Comprehensive Test Runner")
    parser.add_argument("--quick", action="store_true", help="Run only required tests")
    parser.add_argument("--save-report", help="Save detailed report to file")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", 
                       help="Load balancer URL for testing")
    
    args = parser.parse_args()
    
    # Set URL for tests that need it
    os.environ.setdefault("LOAD_BALANCER_URL", args.url)
    
    # Run tests
    runner = ChromaDBTestRunner()
    success = runner.run_all_tests(include_optional=not args.quick)
    
    # Save report if requested
    if args.save_report:
        runner.save_report(args.save_report)
    
    # Exit with appropriate code
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 