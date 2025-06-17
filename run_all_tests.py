#!/usr/bin/env python3
"""
REAL PRODUCTION VALIDATION TESTS
Tests actual functionality that matters to real users, not just API responses
"""

import requests
import time
import json
import sys

class ProductionValidator:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session_id = int(time.time())
        self.test_collections = set()
        self.failures = []
        
    def fail(self, test, reason, details=""):
        self.failures.append({'test': test, 'reason': reason, 'details': details})
        print(f"❌ PRODUCTION FAILURE: {test}")
        print(f"   Reason: {reason}")
        if details:
            print(f"   Details: {details}")
        return False
        
    def validate_json(self, response, operation):
        """Validate response is proper JSON - catch bugs like your CMS encountered"""
        try:
            if response.status_code >= 400:
                return self.fail(operation, f"HTTP error {response.status_code}", response.text[:200])
            return response.json()
        except json.JSONDecodeError:
            return self.fail(operation, "Invalid JSON response - would break real applications", 
                           f"Status: {response.status_code}, Content: {response.text[:100]}")
    
    def test_system_health(self):
        """Test system is actually healthy, not just responding"""
        print("🔍 TESTING: System Health (Real Validation)")
        
        # Test load balancer health
        response = requests.get(f"{self.base_url}/health", timeout=15)
        health_data = self.validate_json(response, "Load Balancer Health")
        if not health_data:
            return False
            
        if health_data.get('status') != 'healthy':
            return self.fail("System Health", f"Unhealthy status: {health_data.get('status')}")
            
        # Test both instances respond
        primary = requests.get("https://chroma-primary.onrender.com/api/v2/heartbeat", timeout=10)
        if primary.status_code != 200:
            return self.fail("Primary Instance", f"Primary unhealthy: {primary.status_code}")
            
        replica = requests.get("https://chroma-replica.onrender.com/api/v2/heartbeat", timeout=10)
        if replica.status_code != 200:
            return self.fail("Replica Instance", f"Replica unhealthy: {replica.status_code}")
            
        print("✅ VALIDATED: System health - load balancer and instances healthy")
        return True
    
    def test_collection_creation(self):
        """Test collections are actually created and replicated"""
        print("🔍 TESTING: Collection Creation & Replication (Real Validation)")
        
        test_collection = f"REAL_TEST_{self.session_id}"
        self.test_collections.add(test_collection)
        
        # Create collection
        response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json={"name": test_collection, "configuration": {"hnsw": {"space": "l2"}}},
            timeout=30
        )
        
        data = self.validate_json(response, "Collection Creation")
        if not data:
            return False
            
        collection_id = data.get('id')
        if not collection_id:
            return self.fail("Collection Creation", "No collection ID returned", str(data))
            
        # Verify on primary instance
        time.sleep(3)
        primary_response = requests.get(
            f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}",
            timeout=15
        )
        
        if primary_response.status_code != 200:
            return self.fail("Primary Replication", f"Collection not on primary: {primary_response.status_code}")
            
        # Verify on replica instance
        replica_response = requests.get(
            f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=15
        )
        
        replica_data = self.validate_json(replica_response, "Replica Verification")
        if not replica_data:
            return False
            
        replica_names = [c['name'] for c in replica_data]
        if test_collection not in replica_names:
            return self.fail("Replica Replication", f"Collection not replicated to replica", f"Replica has: {replica_names}")
            
        print(f"✅ VALIDATED: Collection creation & replication - {collection_id[:8]}... exists on both instances")
        return True
    
    def cleanup(self):
        """Clean up test data"""
        print("🧹 Cleaning up test data...")
        for collection in self.test_collections:
            try:
                requests.delete(f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection}", timeout=30)
            except:
                pass
    
    def run_validation(self):
        """Run production validation"""
        print("🚀 PRODUCTION VALIDATION SUITE")
        print("="*60)
        print(f"URL: {self.base_url}")
        print(f"Session: {self.session_id}")
        print("="*60)
        
        tests = [
            ("System Health", self.test_system_health),
            ("Collection Creation", self.test_collection_creation),
        ]
        
        passed = 0
        try:
            for name, test_func in tests:
                if test_func():
                    passed += 1
                else:
                    print(f"❌ {name} FAILED - Production issue detected")
                    break
        finally:
            self.cleanup()
        
        print(f"\\n{'='*60}")
        print("🏁 RESULTS")
        print(f"✅ Passed: {passed}/{len(tests)}")
        print(f"❌ Failed: {len(tests)-passed}/{len(tests)}")
        
        if self.failures:
            print(f"\\n❌ FAILURES:")
            for f in self.failures:
                print(f"  • {f['test']}: {f['reason']}")
        
        if passed == len(tests):
            print("\\n🎉 PRODUCTION VALIDATION PASSED!")
            return True
        else:
            print("\\n⚠️ PRODUCTION ISSUES DETECTED!")
            return False

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='https://chroma-load-balancer.onrender.com')
    args = parser.parse_args()
    
    validator = ProductionValidator(args.url)
    success = validator.run_validation()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
