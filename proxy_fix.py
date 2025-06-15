#!/usr/bin/env python3
"""
Quick fix for proxy_request function to remove complex kwargs handling
"""

def apply_proxy_fix():
    """Apply simplified proxy_request pattern"""
    
    with open('unified_wal_load_balancer.py', 'r') as f:
        content = f.read()
    
    # Find the proxy_request function and replace with simplified version
    old_proxy_section = """            # Forward request through unified WAL load balancer
            # Handle request data properly like old load balancer
            request_kwargs = {}
            
            # Handle JSON vs raw data properly
            if request.method in ['POST', 'PUT', 'PATCH'] and request.content_length:
                if request.is_json:
                    request_kwargs['json'] = request.get_json()
                else:
                    request_kwargs['data'] = request.get_data()
            
            # Filter out None values before passing to forward_request
            filtered_kwargs = {k: v for k, v in request_kwargs.items() if v is not None}
            
            response = enhanced_wal.forward_request(
                method=request.method,
                path=f"/{path}",
                headers={},  # Let session handle headers properly  
                data=filtered_kwargs.get('data', b''),
                **{k: v for k, v in filtered_kwargs.items() if k != 'data'}  # Pass json, params, etc.
            )"""
    
    new_proxy_section = """            # Forward request using simple pattern like old load balancer
            data = b''
            if request.method in ['POST', 'PUT', 'PATCH'] and request.content_length:
                data = request.get_data()
            
            response = enhanced_wal.forward_request(
                method=request.method,
                path=f"/{path}",
                headers={},  # Let session handle headers
                data=data
            )"""
    
    if old_proxy_section in content:
        content = content.replace(old_proxy_section, new_proxy_section)
        
        with open('unified_wal_load_balancer.py', 'w') as f:
            f.write(content)
        
        print("✅ Applied simplified proxy_request fix")
    else:
        print("❌ Could not find proxy_request section to fix")

if __name__ == '__main__':
    apply_proxy_fix() 