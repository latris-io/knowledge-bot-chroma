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

if __name__ == "__main__":
    success = test_load_balancer_logic()
    if success:
        print("\n🎉 SUCCESS: Load balancer logic works correctly!")
    else:
        print("\n❌ FAILURE: Load balancer logic is broken!") 