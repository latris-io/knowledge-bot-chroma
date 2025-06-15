#!/usr/bin/env python3
"""
Test script to identify current ChromaDB API endpoints
"""
import requests
import json
from urllib.parse import urljoin

def test_chroma_api_endpoints():
    """Test different API endpoints to understand the current structure"""
    
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    # List of potential endpoints to test
    test_endpoints = [
        # Basic info endpoints
        "/",
        "/api",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/health",
        "/heartbeat",
        "/version",
        
        # Potential v1 endpoints
        "/api/v1",
        "/api/v1/version",
        "/api/v1/heartbeat",
        "/api/v1/collections",
        "/api/v1/tenants",
        "/api/v1/databases",
        
        # Potential v2 endpoints (newer ChromaDB versions)
        "/api/v2",
        "/api/v2/version", 
        "/api/v2/heartbeat",
        "/api/v2/collections",
        "/api/v2/tenants",
        "/api/v2/databases",
        
        # Newer API structure patterns
        "/api/v1/tenants/default_tenant/databases/default_database/collections",
        "/api/v2/tenants/default_tenant/databases/default_database/collections",
        
        # Alternative patterns
        "/collections",
        "/tenants",
        "/databases",
    ]
    
    print("=== TESTING CHROMA API ENDPOINTS ===\n")
    
    for instance_name, base_url in [("PRIMARY", primary_url), ("REPLICA", replica_url)]:
        print(f"Testing {instance_name} ({base_url}):")
        
        working_endpoints = []
        
        for endpoint in test_endpoints:
            try:
                url = urljoin(base_url, endpoint)
                response = requests.get(url, timeout=10)
                
                status_code = response.status_code
                if status_code == 200:
                    working_endpoints.append(endpoint)
                    print(f"  ✅ {endpoint} -> {status_code}")
                    
                    # Try to show content for key endpoints
                    if endpoint in ["/api", "/version", "/api/v1/version", "/api/v2/version"]:
                        try:
                            content = response.json()
                            print(f"     Content: {content}")
                        except:
                            content = response.text[:200]
                            if content:
                                print(f"     Content: {content}...")
                elif status_code == 404:
                    print(f"  ❌ {endpoint} -> {status_code} (Not Found)")
                elif status_code == 410:
                    print(f"  ⚠️  {endpoint} -> {status_code} (Gone - Deprecated)")
                else:
                    print(f"  ⚠️  {endpoint} -> {status_code}")
                    
            except requests.exceptions.Timeout:
                print(f"  ⏱️  {endpoint} -> Timeout")
            except requests.exceptions.RequestException as e:
                print(f"  💥 {endpoint} -> Error: {str(e)[:50]}...")
        
        print(f"\n  Working endpoints for {instance_name}: {working_endpoints}\n")
        
        # If we found working endpoints, try to get collections
        if working_endpoints:
            for collections_endpoint in [ep for ep in working_endpoints if 'collections' in ep]:
                try:
                    url = urljoin(base_url, collections_endpoint)
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        print(f"  📋 Collections from {collections_endpoint}:")
                        try:
                            collections = response.json()
                            if isinstance(collections, list):
                                print(f"     Found {len(collections)} collections")
                                for i, col in enumerate(collections[:3]):  # Show first 3
                                    print(f"     [{i}] {col}")
                            else:
                                print(f"     Response: {collections}")
                        except:
                            print(f"     Raw response: {response.text[:200]}...")
                except Exception as e:
                    print(f"  💥 Collections test failed: {e}")
        
        print("-" * 50)

if __name__ == "__main__":
    test_chroma_api_endpoints() 