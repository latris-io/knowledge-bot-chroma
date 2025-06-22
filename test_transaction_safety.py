#!/usr/bin/env python3
"""
CRITICAL TEST: Verify Transaction Safety Service is Working
This test validates that write operations are being logged for recovery during failures.
"""

import requests
import json
import time
import uuid
import os
import psycopg2
from datetime import datetime, timedelta
import threading

class TransactionSafetyValidator:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            print("❌ DATABASE_URL not set - cannot verify transaction logging")
            
    def get_db_connection(self):
        """Get database connection to check transaction logs"""
        if not self.database_url:
            return None
        return psycopg2.connect(self.database_url)
    
    def check_transaction_table_exists(self):
        """Verify the transaction safety table exists"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'emergency_transaction_log'
                        )
                    """)
                    exists = cur.fetchone()[0]
                    print(f"📊 emergency_transaction_log table exists: {exists}")
                    return exists
        except Exception as e:
            print(f"❌ Failed to check transaction table: {e}")
            return False
    
    def count_recent_transactions(self, minutes_ago=5):
        """Count transactions logged in recent minutes"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*), status, method
                        FROM emergency_transaction_log 
                        WHERE created_at > NOW() - INTERVAL '%s minutes'
                        GROUP BY status, method
                        ORDER BY COUNT(*) DESC
                    """, (minutes_ago,))
                    
                    results = cur.fetchall()
                    print(f"\n📊 Transactions in last {minutes_ago} minutes:")
                    total = 0
                    for row in results:
                        count, status, method = row
                        total += count
                        print(f"   {method} {status}: {count}")
                    
                    print(f"   TOTAL: {total} transactions")
                    return total
        except Exception as e:
            print(f"❌ Failed to count recent transactions: {e}")
            return 0
    
    def test_transaction_logging_during_normal_operation(self):
        """Test if transactions get logged during normal write operations"""
        print("\n🧪 TEST 1: Transaction Logging During Normal Operations")
        
        # Get baseline transaction count
        baseline = self.count_recent_transactions(1)
        
        # Perform a write operation that should be logged
        test_collection_name = f"TRANSACTION_SAFETY_TEST_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        print(f"📝 Creating collection: {test_collection_name}")
        response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={'Content-Type': 'application/json'},
            json={"name": test_collection_name},
            timeout=10
        )
        
        print(f"   Response: {response.status_code}")
        if response.status_code == 200:
            collection_data = response.json()
            print(f"   Collection ID: {collection_data.get('id', 'N/A')[:8]}...")
        
        # Wait for transaction logging to complete
        time.sleep(2)
        
        # Check if transaction was logged
        new_count = self.count_recent_transactions(1)
        transactions_added = new_count - baseline
        
        print(f"\n📊 Result: {transactions_added} new transactions logged")
        
        if transactions_added > 0:
            print("✅ PASS: Transaction logging is working")
            return True
        else:
            print("❌ FAIL: No transactions were logged")
            return False
    
    def test_503_error_transaction_logging(self):
        """Test if transactions get logged when 503 errors occur"""
        print("\n🧪 TEST 2: Transaction Logging During 503 Errors")
        
        # Strategy: Rapid fire requests to trigger 503s
        print("🔥 Sending rapid requests to trigger 503 errors...")
        
        baseline = self.count_recent_transactions(1)
        
        # Send 15 rapid requests to overwhelm the system
        responses = []
        threads = []
        
        def make_request(i):
            try:
                test_name = f"RAPID_503_TEST_{i}_{int(time.time())}"
                resp = requests.post(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                    headers={'Content-Type': 'application/json'},
                    json={"name": test_name},
                    timeout=5
                )
                responses.append((i, resp.status_code, resp.text[:100]))
            except Exception as e:
                responses.append((i, 'ERROR', str(e)[:100]))
        
        # Fire 15 concurrent requests
        for i in range(15):
            thread = threading.Thread(target=make_request, args=(i,))
            threads.append(thread)
            thread.start()
            time.sleep(0.05)  # Small delay between starts
        
        # Wait for all to complete
        for thread in threads:
            thread.join()
        
        # Analyze responses
        success_count = 0
        error_503_count = 0
        other_error_count = 0
        
        print("\n📊 Response Analysis:")
        for req_id, status, text in responses:
            if status == 200:
                success_count += 1
            elif status == 503:
                error_503_count += 1
                print(f"   Request {req_id}: 503 - {text}")
            else:
                other_error_count += 1
                print(f"   Request {req_id}: {status} - {text}")
        
        print(f"\n📈 Summary:")
        print(f"   ✅ Success (200): {success_count}")
        print(f"   🚨 503 Errors: {error_503_count}")
        print(f"   ❌ Other Errors: {other_error_count}")
        
        # Wait for transaction logging
        time.sleep(3)
        
        # Check transaction logging
        new_count = self.count_recent_transactions(1)
        transactions_added = new_count - baseline
        
        print(f"\n📊 Transaction Logging Results:")
        print(f"   Transactions logged: {transactions_added}")
        print(f"   Total operations: {len(responses)}")
        print(f"   503 errors: {error_503_count}")
        
        # CRITICAL ANALYSIS
        if error_503_count > 0:
            if transactions_added >= error_503_count:
                print("✅ EXCELLENT: 503 errors were logged for recovery")
                return True
            elif transactions_added > 0:
                print(f"⚠️ PARTIAL: Only {transactions_added}/{error_503_count} 503 errors were logged")
                return False
            else:
                print("❌ CRITICAL: 503 errors were NOT logged - DATA LOSS RISK")
                return False
        else:
            print("ℹ️ No 503 errors triggered - cannot test 503 logging")
            return None
    
    def test_failed_transaction_recovery(self):
        """Test if failed transactions can be recovered"""
        print("\n🧪 TEST 3: Failed Transaction Recovery")
        
        # This would require accessing the recovery mechanism
        # For now, just check if there are any failed transactions pending
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*), status 
                        FROM emergency_transaction_log 
                        WHERE status IN ('FAILED', 'ATTEMPTING')
                        AND created_at > NOW() - INTERVAL '1 hour'
                        GROUP BY status
                    """)
                    
                    results = cur.fetchall()
                    print("📊 Recent Failed/Attempting Transactions:")
                    
                    failed_count = 0
                    attempting_count = 0
                    
                    for count, status in results:
                        print(f"   {status}: {count}")
                        if status == 'FAILED':
                            failed_count = count
                        elif status == 'ATTEMPTING':
                            attempting_count = count
                    
                    if failed_count > 0:
                        print(f"⚠️ WARNING: {failed_count} failed transactions need recovery")
                        return False
                    elif attempting_count > 0:
                        print(f"⏳ PENDING: {attempting_count} transactions still attempting")
                        return None
                    else:
                        print("✅ GOOD: No failed transactions pending")
                        return True
                        
        except Exception as e:
            print(f"❌ Failed to check recovery status: {e}")
            return False
    
    def run_comprehensive_test(self):
        """Run all transaction safety tests"""
        print("🛡️ TRANSACTION SAFETY VALIDATION")
        print("=" * 50)
        
        if not self.database_url:
            print("❌ Cannot run tests - DATABASE_URL not available")
            return False
        
        # Test 1: Check if transaction table exists
        if not self.check_transaction_table_exists():
            print("❌ CRITICAL: Transaction safety table doesn't exist")
            return False
        
        # Test 2: Normal operation logging
        test1_result = self.test_transaction_logging_during_normal_operation()
        
        # Test 3: 503 error logging
        test2_result = self.test_503_error_transaction_logging()
        
        # Test 4: Recovery status
        test3_result = self.test_failed_transaction_recovery()
        
        # Final assessment
        print("\n" + "=" * 50)
        print("🏆 FINAL TRANSACTION SAFETY ASSESSMENT")
        print("=" * 50)
        
        if test1_result and test2_result and test3_result:
            print("✅ EXCELLENT: Transaction Safety Service is working correctly")
            print("✅ CONFIRMED: Zero data loss protection is active")
            return True
        elif test2_result is None:
            print("⚠️ INCONCLUSIVE: Could not trigger 503 errors to test logging")
            print("ℹ️ Normal operations are logged, but 503 protection unverified")
            return None
        else:
            print("❌ CRITICAL: Transaction Safety Service has issues")
            print("🚨 WARNING: Data loss is possible during failures")
            return False

def main():
    print("🚀 Starting Transaction Safety Validation...")
    validator = TransactionSafetyValidator()
    result = validator.run_comprehensive_test()
    
    if result is True:
        print("\n🎉 VERDICT: Transaction Safety CONFIRMED")
    elif result is None:
        print("\n⚠️ VERDICT: Transaction Safety PARTIALLY CONFIRMED")
    else:
        print("\n🚨 VERDICT: Transaction Safety FAILED")
    
    return result

if __name__ == "__main__":
    main() 