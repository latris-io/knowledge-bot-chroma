#!/usr/bin/env python3
"""
Debug script to test 404 detection logic
"""

def test_404_detection():
    # Simulate the error message from the logs
    error_message = "404 Client Error: Not Found for url: https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/2de15961-d0fe-4415-8b65-9aabae669bc3/get"
    
    print("🔍 Testing 404 Detection Logic")
    print("=" * 50)
    print(f"Error message: {error_message}")
    print()
    
    # Test detection methods
    method1 = "404 Client Error" in error_message
    method2 = "Not Found" in error_message
    method3 = "404" in error_message
    
    print(f"Method 1 - '404 Client Error' in message: {method1}")
    print(f"Method 2 - 'Not Found' in message: {method2}")
    print(f"Method 3 - '404' in message: {method3}")
    print()
    
    # Test path detection
    test_paths = [
        "/api/v2/tenants/default_tenant/databases/default_database/collections/2de15961-d0fe-4415-8b65-9aabae669bc3/get",
        "/api/v2/tenants/default_tenant/databases/default_database/collections/2de15961-d0fe-4415-8b65-9aabae669bc3/query"
    ]
    
    for path in test_paths:
        get_match = "/get" in path
        query_match = "/query" in path
        print(f"Path: {path}")
        print(f"  Contains '/get': {get_match}")
        print(f"  Contains '/query': {query_match}")
        print(f"  Would trigger graceful skip: {get_match or query_match}")
        print()

if __name__ == "__main__":
    test_404_detection() 