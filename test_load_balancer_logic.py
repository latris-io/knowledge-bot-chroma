#!/usr/bin/env python3
"""
Test script to mimic exactly what the load balancer should be doing
"""

import requests
import json

def test_load_balancer_logic():
    """Test the exact same logic the load balancer uses"""
    print("🔍 Testing load balancer logic - mimicking exact request pattern...")
    
    # This mimics what the load balancer should do
    url = "https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/11119310-d2f6-477a-872d-5dc6f373e805/get"
    
    # Mimic the request parameters that load balancer uses
    req_params = {"timeout": 30}
    req_params["json"] = {"limit": 500, "include": ["documents", "metadatas"]}
    
    # Mimic the headers that load balancer should send
    headers = {
        'Content-Type': 'application/json',
        'Accept-Encoding': 'identity'  # This is the key header
    }
    req_params["headers"] = headers
    
    print(f"🔧 Sending headers: {headers}")
    print(f"🔧 Sending JSON: {req_params['json']}")
    
    try:
        response = requests.request("POST", url, **req_params)
        
        print(f"🔧 Response status: {response.status_code}")
        print(f"🔧 Response headers: {dict(response.headers)}")
        print(f"🔧 Content-Encoding: {response.headers.get('content-encoding', 'none')}")
        print(f"🔧 Response.content length: {len(response.content)}")
        print(f"🔧 Response.text length: {len(response.text)}")
        print(f"🔧 First 50 chars of response.text: {repr(response.text[:50])}")
        
        # Check if we get clean JSON
        try:
            json_data = json.loads(response.text)
            print("✅ Load balancer logic produces valid JSON:")
            print(json.dumps(json_data, indent=2))
            return True
        except:
            print("❌ Load balancer logic produces invalid JSON")
            print(f"Full response.text: {repr(response.text)}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_delete_operations():
    """Test that DELETE operations work correctly with proper headers"""
    print("🗑️  Testing DELETE operations...")
    
    try:
        # Test DELETE with proper headers (should get 404, not 400)
        import requests
        
        delete_url = "https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/test-nonexistent-collection"
        
        headers = {
            'Accept': 'application/json'
            # Note: No Content-Type header for DELETE without body
        }
        
        response = requests.delete(delete_url, headers=headers, timeout=30)
        
        # Should get 404 (not found) not 400 (bad request)
        if response.status_code == 404:
            print("✅ DELETE operations working correctly - proper 404 response")
            return True
        elif response.status_code == 400:
            print("❌ DELETE operations still failing with 400 Bad Request")
            return False
        else:
            print(f"⚠️  Unexpected response code: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ DELETE test failed: {e}")
        return False

if __name__ == "__main__":
    test_load_balancer_logic()
    test_delete_operations() 