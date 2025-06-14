#!/usr/bin/env python3
"""
ChromaDB Deployment Diagnostics
Helps troubleshoot deployment timeouts and health check issues
"""

import requests
import time
import json
from datetime import datetime

def check_service(service_name, url, timeout=10):
    """Check if a service is responding"""
    print(f"\n🔍 Checking {service_name}...")
    print(f"   URL: {url}")
    
    try:
        response = requests.get(url, timeout=timeout)
        print(f"   ✅ Status: {response.status_code}")
        print(f"   📊 Response time: {response.elapsed.total_seconds():.2f}s")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                data = response.json()
                print(f"   📄 Response: {json.dumps(data, indent=2)}")
            except:
                print(f"   📄 Response: {response.text[:200]}...")
        else:
            print(f"   📄 Response: {response.text[:200]}...")
            
        return True, response.status_code
        
    except requests.exceptions.ConnectTimeout:
        print(f"   ❌ Connection timeout after {timeout}s")
        return False, "timeout"
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ Connection error: {str(e)}")
        return False, "connection_error"
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False, "error"

def wait_for_service(service_name, url, max_wait=300, check_interval=10):
    """Wait for a service to become healthy"""
    print(f"\n⏳ Waiting for {service_name} to become healthy...")
    print(f"   Max wait time: {max_wait}s")
    print(f"   Check interval: {check_interval}s")
    
    start_time = time.time()
    attempt = 1
    
    while time.time() - start_time < max_wait:
        print(f"\n   Attempt {attempt} ({int(time.time() - start_time)}s elapsed)")
        
        success, status = check_service(service_name, url, timeout=15)
        
        if success and status == 200:
            elapsed = time.time() - start_time
            print(f"   🎉 {service_name} is healthy! (took {elapsed:.1f}s)")
            return True
        
        print(f"   ⏰ Waiting {check_interval}s before next check...")
        time.sleep(check_interval)
        attempt += 1
    
    print(f"   ⚠️ {service_name} did not become healthy within {max_wait}s")
    return False

def diagnose_chromadb_deployment():
    """Main diagnostic function"""
    print("🩺 ChromaDB Deployment Diagnostics")
    print("=" * 50)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    services = [
        ("Primary ChromaDB", "https://chroma-primary.onrender.com/api/v2/version"),
        ("Replica ChromaDB", "https://chroma-replica.onrender.com/api/v2/version"),
        ("Load Balancer", "https://chroma-load-balancer.onrender.com/health"),
    ]
    
    results = {}
    
    # Quick check of all services
    print("\n🚀 Quick Health Check")
    print("-" * 30)
    
    for service_name, url in services:
        success, status = check_service(service_name, url, timeout=15)
        results[service_name] = {"success": success, "status": status}
    
    # Check if any services need more time
    failed_services = [name for name, result in results.items() if not result["success"]]
    
    if failed_services:
        print(f"\n⚠️ {len(failed_services)} service(s) not responding yet:")
        for service in failed_services:
            print(f"   - {service}")
        
        print(f"\n⏳ Services might still be starting up...")
        print(f"   ChromaDB can take 60-120 seconds to fully initialize")
        
        # Wait for failed services
        for service_name, url in services:
            if service_name in failed_services:
                success = wait_for_service(service_name, url, max_wait=180, check_interval=15)
                results[service_name] = {"success": success, "status": "healthy" if success else "unhealthy"}
    
    # Final summary
    print("\n📊 Final Results")
    print("=" * 50)
    
    healthy_count = sum(1 for result in results.values() if result["success"])
    total_count = len(results)
    
    for service_name, result in results.items():
        status_icon = "✅" if result["success"] else "❌"
        print(f"{status_icon} {service_name}: {'Healthy' if result['success'] else 'Unhealthy'}")
    
    print(f"\n📈 Overall Health: {healthy_count}/{total_count} services healthy")
    
    # Recommendations
    print("\n💡 Recommendations")
    print("-" * 30)
    
    if healthy_count == total_count:
        print("🎉 All services are healthy! Your deployment is successful.")
    elif healthy_count == 0:
        print("⚠️ No services are responding. Check:")
        print("   - Services are deployed and running in Render dashboard")
        print("   - No build errors in deployment logs")
        print("   - Dockerfile health check timeout is sufficient")
    else:
        print(f"⚠️ {total_count - healthy_count} service(s) not healthy. Check:")
        print("   - Individual service logs in Render dashboard")
        print("   - Service dependencies and environment variables")
        print("   - Network connectivity between services")
    
    print("\n🔧 Troubleshooting Tips:")
    print("   1. Check Render dashboard for service status")
    print("   2. Review service logs for error messages")
    print("   3. Verify environment variables are set correctly")
    print("   4. Ensure services have enough time to start (60-120s)")
    print("   5. Check if health check endpoints are accessible")
    
    return results

if __name__ == "__main__":
    try:
        results = diagnose_chromadb_deployment()
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"diagnosis_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": results
            }, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Diagnostics interrupted by user")
    except Exception as e:
        print(f"\n❌ Diagnostic error: {str(e)}") 