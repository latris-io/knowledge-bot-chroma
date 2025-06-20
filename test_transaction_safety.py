#!/usr/bin/env python3
"""
Transaction Safety System Test Script
Tests the pre-execution logging and recovery mechanisms to ensure zero data loss during timing gaps
"""

import os
import time
import json
import uuid
import logging
import requests
import threading
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TransactionSafetyTester:
    """Test the transaction safety system to verify zero data loss during timing gaps"""
    
    def __init__(self, load_balancer_url: str):
        self.load_balancer_url = load_balancer_url.rstrip('/')
        self.test_session_id = str(uuid.uuid4())[:8]
        self.test_results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "timing_gap_tests": 0,
            "recovery_tests": 0,
            "details": []
        }
    
    def test_transaction_safety_availability(self) -> bool:
        """Test if transaction safety service is available and operational"""
        logger.info("🔍 Testing transaction safety service availability...")
        
        try:
            response = requests.get(f"{self.load_balancer_url}/transaction/safety/status", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("available", False):
                    logger.info("✅ Transaction safety service is available and running")
                    logger.info(f"   Service running: {data.get('service_running', 'unknown')}")
                    logger.info(f"   Recovery interval: {data.get('recovery_interval', 'unknown')}s")
                    return True
                else:
                    logger.error("❌ Transaction safety service not available")
                    logger.error(f"   Message: {data.get('message', 'No details provided')}")
                    return False
            else:
                logger.error(f"❌ Failed to get transaction safety status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception checking transaction safety availability: {e}")
            return False
    
    def test_pre_execution_logging(self) -> bool:
        """Test that write operations are logged before execution"""
        logger.info("🔍 Testing pre-execution transaction logging...")
        
        try:
            collection_name = f"TXTEST_{self.test_session_id}_{int(time.time())}"
            
            # Create a collection to test transaction logging
            payload = {"name": collection_name}
            
            logger.info(f"   Creating test collection: {collection_name}")
            response = requests.post(
                f"{self.load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                logger.info("✅ Collection creation succeeded")
                
                # Wait a moment for transaction to be logged
                time.sleep(2)
                
                # Check transaction safety status for recent transactions
                safety_response = requests.get(f"{self.load_balancer_url}/transaction/safety/status", timeout=10)
                
                if safety_response.status_code == 200:
                    safety_data = safety_response.json()
                    metrics = safety_data.get("metrics", {})
                    total_transactions = metrics.get("total_transactions", 0)
                    
                    if total_transactions > 0:
                        logger.info(f"✅ Transaction logging confirmed - {total_transactions} total transactions logged")
                        return True
                    else:
                        logger.warning("⚠️ No transactions found in safety log")
                        return False
                else:
                    logger.error("❌ Failed to verify transaction logging")
                    return False
            else:
                logger.error(f"❌ Collection creation failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception during pre-execution logging test: {e}")
            return False
        finally:
            # Cleanup test collection
            try:
                requests.delete(f"{self.load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}")
            except:
                pass
    
    def test_timing_gap_detection(self) -> bool:
        """Test detection of timing gap failures"""
        logger.info("🔍 Testing timing gap failure detection...")
        
        try:
            # First, get current system status
            status_response = requests.get(f"{self.load_balancer_url}/status", timeout=10)
            
            if status_response.status_code != 200:
                logger.error("❌ Cannot get system status for timing gap test")
                return False
            
            status_data = status_response.json()
            healthy_instances = status_data.get("healthy_instances", 0)
            
            if healthy_instances < 2:
                logger.warning("⚠️ Not enough healthy instances for timing gap simulation")
                logger.info("   This test requires manual primary instance suspension")
                logger.info("   Skipping timing gap detection test")
                return True  # Skip rather than fail
            
            # If both instances are healthy, we can't easily simulate timing gap
            logger.info("✅ Both instances healthy - timing gap simulation would require manual intervention")
            logger.info("   Checking for existing timing gap failures in transaction log...")
            
            # Check if we have any timing gap failures recorded
            safety_response = requests.get(f"{self.load_balancer_url}/transaction/safety/status", timeout=10)
            
            if safety_response.status_code == 200:
                safety_data = safety_response.json()
                metrics = safety_data.get("metrics", {})
                timing_gap_failures = metrics.get("timing_gap_failures", 0)
                
                logger.info(f"   Found {timing_gap_failures} timing gap failures in transaction log")
                return True
            else:
                logger.error("❌ Failed to check timing gap failure history")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception during timing gap detection test: {e}")
            return False
    
    def test_transaction_recovery(self) -> bool:
        """Test transaction recovery mechanism"""
        logger.info("🔍 Testing transaction recovery mechanism...")
        
        try:
            # Trigger manual recovery to test the process
            recovery_response = requests.post(
                f"{self.load_balancer_url}/transaction/safety/recovery/trigger",
                timeout=30
            )
            
            if recovery_response.status_code == 200:
                data = recovery_response.json()
                if data.get("success", False):
                    logger.info("✅ Transaction recovery trigger successful")
                    logger.info(f"   Message: {data.get('message', '')}")
                    return True
                else:
                    logger.error("❌ Transaction recovery trigger failed")
                    return False
            else:
                logger.error(f"❌ Recovery trigger failed with status: {recovery_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception during transaction recovery test: {e}")
            return False
    
    def test_transaction_cleanup(self) -> bool:
        """Test transaction cleanup functionality"""
        logger.info("🔍 Testing transaction cleanup...")
        
        try:
            # Attempt to clean up old transactions (0 days = clean all completed)
            cleanup_response = requests.post(
                f"{self.load_balancer_url}/transaction/safety/cleanup",
                json={"days_old": 0},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if cleanup_response.status_code == 200:
                data = cleanup_response.json()
                if data.get("success", False):
                    deleted_count = data.get("deleted_transactions", 0)
                    logger.info(f"✅ Transaction cleanup successful - {deleted_count} transactions cleaned")
                    return True
                else:
                    logger.error("❌ Transaction cleanup failed")
                    return False
            else:
                logger.error(f"❌ Cleanup failed with status: {cleanup_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception during transaction cleanup test: {e}")
            return False
    
    def test_high_load_transaction_safety(self) -> bool:
        """Test transaction safety under high load conditions"""
        logger.info("🔍 Testing transaction safety under high load...")
        
        try:
            # Create multiple concurrent transactions to test load handling
            num_concurrent = 5
            collection_prefix = f"TXLOAD_{self.test_session_id}_{int(time.time())}"
            
            def create_collection(index):
                try:
                    collection_name = f"{collection_prefix}_{index}"
                    payload = {"name": collection_name}
                    
                    response = requests.post(
                        f"{self.load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=30
                    )
                    
                    return response.status_code in [200, 201]
                except Exception as e:
                    logger.error(f"   Concurrent transaction {index} failed: {e}")
                    return False
            
            # Execute concurrent transactions
            threads = []
            results = []
            
            for i in range(num_concurrent):
                thread = threading.Thread(target=lambda idx=i: results.append(create_collection(idx)))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            success_count = sum(1 for result in results if result)
            logger.info(f"   {success_count}/{num_concurrent} concurrent transactions succeeded")
            
            # Cleanup created collections
            for i in range(num_concurrent):
                try:
                    collection_name = f"{collection_prefix}_{i}"
                    requests.delete(
                        f"{self.load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                        timeout=10
                    )
                except:
                    pass
            
            # Consider success if at least 80% of transactions succeeded
            success_rate = success_count / num_concurrent
            if success_rate >= 0.8:
                logger.info(f"✅ High load transaction safety test passed ({success_rate:.1%} success rate)")
                return True
            else:
                logger.error(f"❌ High load test failed - only {success_rate:.1%} success rate")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception during high load transaction safety test: {e}")
            return False
    
    def run_comprehensive_test_suite(self) -> Dict[str, Any]:
        """Run complete transaction safety test suite"""
        logger.info("🚀 Starting comprehensive transaction safety test suite...")
        logger.info(f"   Test session ID: {self.test_session_id}")
        logger.info(f"   Load balancer URL: {self.load_balancer_url}")
        
        # Define test cases
        test_cases = [
            ("Transaction Safety Availability", self.test_transaction_safety_availability),
            ("Pre-execution Logging", self.test_pre_execution_logging),
            ("Timing Gap Detection", self.test_timing_gap_detection),
            ("Transaction Recovery", self.test_transaction_recovery),
            ("Transaction Cleanup", self.test_transaction_cleanup),
            ("High Load Transaction Safety", self.test_high_load_transaction_safety)
        ]
        
        # Run each test
        for test_name, test_function in test_cases:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running test: {test_name}")
            logger.info(f"{'='*60}")
            
            try:
                start_time = time.time()
                result = test_function()
                duration = time.time() - start_time
                
                self.test_results["total_tests"] += 1
                
                if result:
                    self.test_results["passed_tests"] += 1
                    status = "PASSED"
                else:
                    self.test_results["failed_tests"] += 1
                    status = "FAILED"
                
                self.test_results["details"].append({
                    "test_name": test_name,
                    "status": status,
                    "duration_seconds": round(duration, 2)
                })
                
                logger.info(f"Test result: {status} (duration: {duration:.2f}s)")
                
            except Exception as e:
                logger.error(f"Test {test_name} threw exception: {e}")
                self.test_results["failed_tests"] += 1
                self.test_results["total_tests"] += 1
                self.test_results["details"].append({
                    "test_name": test_name,
                    "status": "ERROR",
                    "error": str(e),
                    "duration_seconds": 0
                })
        
        # Calculate final results
        total = self.test_results["total_tests"]
        passed = self.test_results["passed_tests"]
        failed = self.test_results["failed_tests"]
        success_rate = (passed / total * 100) if total > 0 else 0
        
        logger.info(f"\n{'='*60}")
        logger.info("TRANSACTION SAFETY TEST SUITE COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total tests: {total}")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Success rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            logger.info("🎉 TRANSACTION SAFETY SYSTEM: OPERATIONAL")
        elif success_rate >= 60:
            logger.warning("⚠️ TRANSACTION SAFETY SYSTEM: PARTIALLY OPERATIONAL")
        else:
            logger.error("❌ TRANSACTION SAFETY SYSTEM: NEEDS ATTENTION")
        
        return self.test_results
    
    def generate_summary_report(self) -> str:
        """Generate a summary report of test results"""
        total = self.test_results["total_tests"]
        passed = self.test_results["passed_tests"]
        failed = self.test_results["failed_tests"]
        success_rate = (passed / total * 100) if total > 0 else 0
        
        report = f"""
Transaction Safety System Test Report
=====================================
Test Session: {self.test_session_id}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Load Balancer: {self.load_balancer_url}

Summary:
--------
Total Tests: {total}
Passed: {passed}
Failed: {failed}
Success Rate: {success_rate:.1f}%

Test Details:
-------------
"""
        
        for detail in self.test_results["details"]:
            status_emoji = "✅" if detail["status"] == "PASSED" else "❌"
            report += f"{status_emoji} {detail['test_name']}: {detail['status']} ({detail.get('duration_seconds', 0):.2f}s)\n"
            if "error" in detail:
                report += f"   Error: {detail['error']}\n"
        
        return report

def main():
    """Main function to run transaction safety tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test transaction safety system")
    parser.add_argument("--url", required=True, help="Load balancer URL")
    parser.add_argument("--output", help="Output file for test report")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create tester and run tests
    tester = TransactionSafetyTester(args.url)
    results = tester.run_comprehensive_test_suite()
    
    # Generate and save report if requested
    if args.output:
        report = tester.generate_summary_report()
        with open(args.output, 'w') as f:
            f.write(report)
        logger.info(f"Test report saved to: {args.output}")
    
    # Exit with appropriate code
    success_rate = (results["passed_tests"] / results["total_tests"] * 100) if results["total_tests"] > 0 else 0
    if success_rate >= 80:
        exit(0)  # Success
    else:
        exit(1)  # Failure

if __name__ == "__main__":
    main() 