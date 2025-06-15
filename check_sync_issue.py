#!/usr/bin/env python3
import requests
import json

def check_chroma_instances():
    """Check what's in both primary and replica instances"""
    
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    print("=== CHECKING CHROMA INSTANCES ===\n")
    
    # Check heartbeat first (try v2 API)
    try:
        primary_heartbeat = requests.get(f"{primary_url}/api/v1/heartbeat", timeout=10)
        print(f"Primary heartbeat (v1): {primary_heartbeat.status_code}")
        
        # Try alternative endpoints
        try:
            primary_version = requests.get(f"{primary_url}/api/v1/version", timeout=10)
            print(f"Primary version: {primary_version.status_code}")
            if primary_version.status_code == 200:
                print(f"  Version info: {primary_version.json()}")
        except:
            pass
        
        replica_heartbeat = requests.get(f"{replica_url}/api/v1/heartbeat", timeout=10)
        print(f"Replica heartbeat (v1): {replica_heartbeat.status_code}")
        
        # Try alternative endpoints
        try:
            replica_version = requests.get(f"{replica_url}/api/v1/version", timeout=10)
            print(f"Replica version: {replica_version.status_code}")
            if replica_version.status_code == 200:
                print(f"  Version info: {replica_version.json()}")
        except:
            pass
            
    except Exception as e:
        print(f"Heartbeat error: {e}")
    
    print()
    
    # List collections using multiple API approaches
    try:
        # Try different API endpoints
        for api_version in ['v1', 'v2']:
            print(f"=== Trying API {api_version} ===")
            
            # Primary collections
            primary_collections = requests.get(f"{primary_url}/api/{api_version}/collections", timeout=10)
            print(f"Primary collections ({api_version}): {primary_collections.status_code}")
            if primary_collections.status_code == 200:
                primary_data = primary_collections.json()
                print(f"Primary collections: {len(primary_data) if isinstance(primary_data, list) else 'Error'}")
                if isinstance(primary_data, list):
                    for collection in primary_data[:5]:  # Show first 5
                        print(f"  - {collection.get('name', 'Unknown')}")
                break  # Success, stop trying other versions
            else:
                print(f"Primary error ({api_version}): {primary_collections.text[:200]}")
                
            # Replica collections  
            replica_collections = requests.get(f"{replica_url}/api/{api_version}/collections", timeout=10)
            print(f"Replica collections ({api_version}): {replica_collections.status_code}")
            if replica_collections.status_code == 200:
                replica_data = replica_collections.json()
                print(f"Replica collections: {len(replica_data) if isinstance(replica_data, list) else 'Error'}")
                if isinstance(replica_data, list):
                    for collection in replica_data[:5]:  # Show first 5
                        print(f"  - {collection.get('name', 'Unknown')}")
                break  # Success, stop trying other versions
            else:
                print(f"Replica error ({api_version}): {replica_collections.text[:200]}")
            
            print()
            
    except Exception as e:
        print(f"Collections check error: {e}")
    
    print()
    
    # Check if there's any specific collection we can examine
    # Since API v1 is deprecated, let's see what other endpoints work
    try:
        print("=== Checking available endpoints ===")
        
        # Try some common endpoints that might work
        test_endpoints = [
            "/api/v1/pre-flight-checks",
            "/api/v1/reset",
            "/health",
            "/docs",
            "/"
        ]
        
        for endpoint in test_endpoints:
            try:
                response = requests.get(f"{primary_url}{endpoint}", timeout=5)
                print(f"Primary {endpoint}: {response.status_code}")
                if response.status_code == 200 and len(response.text) < 500:
                    print(f"  Response: {response.text[:100]}...")
            except:
                pass
                
    except Exception as e:
        print(f"Endpoint check error: {e}")

def check_load_balancer_status():
    """Check load balancer status and pending operations"""
    try:
        lb_health = requests.get("https://chroma-load-balancer.onrender.com/health", timeout=10)
        if lb_health.status_code == 200:
            health_data = lb_health.json()
            print("Load Balancer Status:")
            print(f"  Status: {health_data.get('status')}")
            print(f"  Healthy instances: {health_data.get('healthy_instances')}")
            print(f"  Pending writes: {health_data.get('pending_writes')}")
            print(f"  Architecture: {health_data.get('architecture')}")
        else:
            print(f"Load balancer health check failed: {lb_health.status_code}")
    except Exception as e:
        print(f"Load balancer check error: {e}")

if __name__ == "__main__":
    check_load_balancer_status()
    print()
    check_chroma_instances() 