#!/usr/bin/env python3
"""
Quick fix for proxy_request function to return JSON data directly
"""

def apply_fix():
    with open('unified_wal_load_balancer.py', 'r') as f:
        content = f.read()
    
    # Find and replace the problematic return section
    old_section = '''            # Return the raw requests.Response for proxy_request to handle
            flask_response = Response(
                response.content if hasattr(response, "content") else response.data,
                status=response.status_code if hasattr(response, "status_code") else 200,
                headers=[(key, value) for key, value in response.headers if hasattr(response, "headers") else {}.items() if key.lower() not in ['content-encoding', 'transfer-encoding']]
            )
            
            # Ensure content-type is set
            if 'application/json' not in flask_response.headers if hasattr(response, "headers") else {}.get('Content-Type', ''):
                flask_response.headers if hasattr(response, "headers") else {}['Content-Type'] = 'application/json'
                
            return response'''
    
    new_section = '''            # Return JSON data directly - Flask handles this automatically
            try:
                import json
                json_data = json.loads(response.content.decode('utf-8'))
                return json_data, response.status_code
            except:
                # If not JSON, return raw content with proper headers
                flask_response = Response(
                    response.content,
                    status=response.status_code,
                    headers=dict(response.headers),
                    mimetype='application/json'
                )
                return flask_response'''
    
    if old_section in content:
        content = content.replace(old_section, new_section)
        with open('unified_wal_load_balancer.py', 'w') as f:
            f.write(content)
        print("✅ Fixed proxy_request to return JSON directly")
    else:
        print("❌ Could not find the section to replace")

if __name__ == "__main__":
    apply_fix() 