#!/usr/bin/env python3
"""
Quick fix for DELETE operation failover issues
This script patches the DELETE logic to be simpler and more robust
"""

import re

def fix_delete_failover():
    """Fix the overly complex DELETE logic that's causing failover failures"""
    
    # Read the current file
    with open('unified_wal_load_balancer.py', 'r') as f:
        content = f.read()
    
    # Find the DELETE section and replace with simplified logic
    delete_start = 'if method == "DELETE":'
    delete_end = 'logger.error(f"❌ DELETE failed on both instances")'
    
    # Find the start and end positions
    start_pos = content.find(delete_start)
    if start_pos == -1:
        print("❌ Could not find DELETE section start")
        return False
    
    # Find the end of the DELETE block by looking for the next major section
    end_search = content.find('# For non-DELETE write operations', start_pos)
    if end_search == -1:
        print("❌ Could not find DELETE section end")
        return False
    
    # Extract the part before and after the DELETE section
    before_delete = content[:start_pos]
    after_delete = content[end_search:]
    
    # Create simplified DELETE logic
    simplified_delete = '''if method == "DELETE":
            logger.info(f"🗑️ SIMPLIFIED DELETE - trying all healthy instances")
            
            # Get all healthy instances
            healthy_instances = self.get_healthy_instances()
            if not healthy_instances:
                from requests import Response
                error_response = Response()
                error_response.status_code = 503
                error_response._content = json.dumps({
                    "error": "No healthy instances available"
                }).encode()
                logger.error(f"❌ DELETE failed: No healthy instances")
                return error_response
            
            # Try DELETE on all healthy instances using original path
            results = []
            for instance in healthy_instances:
                try:
                    url = f"{instance.url}{path}"
                    logger.info(f"   🔄 DELETE {instance.name}: {url}")
                    
                    response = requests.request(method, url, 
                                              headers=headers or {}, 
                                              data=data, 
                                              timeout=30, 
                                              **kwargs)
                    
                    success = response.status_code in [200, 204, 404]
                    results.append({
                        "instance": instance.name,
                        "status": response.status_code,
                        "success": success
                    })
                    
                    logger.info(f"   {'✅' if success else '❌'} {instance.name}: {response.status_code}")
                    
                except Exception as e:
                    results.append({
                        "instance": instance.name,
                        "error": str(e),
                        "success": False
                    })
                    logger.error(f"   ❌ {instance.name} exception: {e}")
            
            # Success if any instance succeeded
            successful = [r for r in results if r.get("success", False)]
            
            if successful:
                from requests import Response
                success_response = Response()
                success_response.status_code = 200 if len(successful) == len(healthy_instances) else 207
                success_response._content = json.dumps({
                    "success": True,
                    "instances_succeeded": len(successful),
                    "instances_total": len(healthy_instances),
                    "results": results
                }).encode()
                logger.info(f"✅ DELETE success: {len(successful)}/{len(healthy_instances)} instances")
                return success_response
            else:
                from requests import Response
                error_response = Response()
                error_response.status_code = 503
                error_response._content = json.dumps({
                    "error": "DELETE failed on all instances",
                    "results": results
                }).encode()
                logger.error(f"❌ DELETE failed on all {len(healthy_instances)} instances")
                return error_response
        
        '''
    
    # Combine the parts
    new_content = before_delete + simplified_delete + after_delete
    
    # Write the fixed content
    with open('unified_wal_load_balancer.py', 'w') as f:
        f.write(new_content)
    
    print("✅ DELETE failover logic simplified and fixed!")
    print("🔧 Changes made:")
    print("   - Removed complex UUID→name conversion logic")
    print("   - Simplified to try DELETE on all healthy instances") 
    print("   - No dependency on collection mappings")
    print("   - Robust failover that works even without mappings")
    
    return True

if __name__ == "__main__":
    if fix_delete_failover():
        print("\n🚀 DELETE failover fix applied successfully!")
        print("💡 Your CMS DELETE operations should now work during failover")
    else:
        print("\n❌ Failed to apply DELETE failover fix") 