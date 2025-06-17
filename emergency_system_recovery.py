#!/usr/bin/env python3
"""
Emergency System Recovery - Restore ChromaDB system health
Fixes PostgreSQL connection issues and restores healthy instances
"""

import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmergencySystemRecovery:
    """Emergency recovery for ChromaDB system health issues"""
    
    def __init__(self, load_balancer_url="https://chroma-load-balancer.onrender.com"):
        self.load_balancer_url = load_balancer_url.rstrip('/')
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
    
    def check_instance_direct_health(self, instance_url, instance_name):
        """Check instance health directly"""
        logger.info(f"🔍 Checking {instance_name} health directly...")
        
        try:
            # Try direct health check
            health_response = requests.get(f"{instance_url}/api/v2/heartbeat", timeout=15)
            logger.info(f"  {instance_name} heartbeat: {health_response.status_code}")
            
            if health_response.status_code == 200:
                logger.info(f"  ✅ {instance_name} is healthy")
                return True
            else:
                logger.warning(f"  ⚠️ {instance_name} unhealthy: {health_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"  ❌ {instance_name} unreachable: {e}")
            return False
    
    def force_health_refresh(self):
        """Force load balancer to refresh instance health"""
        logger.info("🔄 Forcing load balancer health refresh...")
        
        try:
            # Multiple status checks to trigger health refresh
            for i in range(3):
                status_response = requests.get(f"{self.load_balancer_url}/status", timeout=30)
                if status_response.status_code == 200:
                    status = status_response.json()
                    healthy_instances = status.get('healthy_instances', 0)
                    logger.info(f"  Attempt {i+1}: {healthy_instances}/2 healthy instances")
                    
                    if healthy_instances >= 2:
                        logger.info("  ✅ Both instances healthy!")
                        return True
                        
                    time.sleep(10)  # Wait before next check
                else:
                    logger.warning(f"  ⚠️ Status check failed: {status_response.status_code}")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Health refresh failed: {e}")
            return False
    
    def clear_wal_issues(self):
        """Clear any WAL issues that might be affecting health"""
        logger.info("🧹 Clearing WAL issues...")
        
        try:
            # Clear failed WAL entries
            cleanup_response = requests.post(
                f"{self.load_balancer_url}/wal/cleanup",
                json={"max_age_hours": 0},
                timeout=30
            )
            
            if cleanup_response.status_code == 200:
                result = cleanup_response.json()
                logger.info(f"  ✅ Cleared {result.get('deleted_entries', 0)} WAL entries")
                return True
            else:
                logger.warning(f"  ⚠️ WAL cleanup failed: {cleanup_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ WAL cleanup error: {e}")
            return False
    
    def test_basic_operations(self):
        """Test if basic operations work after recovery"""
        logger.info("🧪 Testing basic operations...")
        
        try:
            # Test collection listing
            collections_response = requests.get(
                f"{self.load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            
            if collections_response.status_code == 200:
                collections = collections_response.json()
                logger.info(f"  ✅ Collection listing works: {len(collections)} collections")
                return True
            else:
                logger.warning(f"  ⚠️ Collection listing failed: {collections_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Basic operations test failed: {e}")
            return False
    
    def comprehensive_recovery(self):
        """Run comprehensive system recovery"""
        logger.info("🚀 Starting Emergency System Recovery")
        logger.info("="*50)
        
        recovery_results = {
            'direct_health_check': False,
            'health_refresh': False,
            'wal_cleanup': False,
            'basic_operations': False
        }
        
        # Step 1: Check direct instance health
        logger.info("\n1️⃣ Direct Instance Health Check")
        primary_healthy = self.check_instance_direct_health(self.primary_url, "Primary")
        replica_healthy = self.check_instance_direct_health(self.replica_url, "Replica")
        
        if primary_healthy and replica_healthy:
            recovery_results['direct_health_check'] = True
            logger.info("✅ Both instances are directly healthy")
        else:
            logger.warning("⚠️ One or both instances are unhealthy")
        
        # Step 2: Clear WAL issues
        logger.info("\n2️⃣ WAL System Cleanup")
        recovery_results['wal_cleanup'] = self.clear_wal_issues()
        
        # Step 3: Force health refresh
        logger.info("\n3️⃣ Load Balancer Health Refresh")
        recovery_results['health_refresh'] = self.force_health_refresh()
        
        # Step 4: Test basic operations
        logger.info("\n4️⃣ Basic Operations Test")
        recovery_results['basic_operations'] = self.test_basic_operations()
        
        # Recovery assessment
        logger.info("\n" + "="*50)
        logger.info("📊 RECOVERY ASSESSMENT")
        logger.info("="*50)
        
        for step, success in recovery_results.items():
            status = "✅ SUCCESS" if success else "❌ FAILED"
            logger.info(f"{status} {step.replace('_', ' ').title()}")
        
        successful_steps = sum(recovery_results.values())
        total_steps = len(recovery_results)
        
        if successful_steps >= 3:
            logger.info(f"\n🎉 RECOVERY SUCCESSFUL ({successful_steps}/{total_steps} steps passed)")
            logger.info("🚀 System should be operational for testing")
            return True
        elif successful_steps >= 2:
            logger.warning(f"\n⚠️ PARTIAL RECOVERY ({successful_steps}/{total_steps} steps passed)")
            logger.info("🔧 System may be partially functional")
            return False
        else:
            logger.error(f"\n❌ RECOVERY FAILED ({successful_steps}/{total_steps} steps passed)")
            logger.info("🛠️ Manual intervention required")
            return False

def main():
    """Run emergency system recovery"""
    recovery = EmergencySystemRecovery()
    
    try:
        success = recovery.comprehensive_recovery()
        
        if success:
            logger.info("\n🎯 NEXT STEPS:")
            logger.info("1. Run test suite to verify functionality")
            logger.info("2. Check if UUID validation fix is now active")
            logger.info("3. Monitor system stability")
        else:
            logger.info("\n🛠️ MANUAL INTERVENTION NEEDED:")
            logger.info("1. Check Render.com service logs")
            logger.info("2. Restart services manually if needed")
            logger.info("3. Verify PostgreSQL connectivity")
        
        return success
        
    except Exception as e:
        logger.error(f"Emergency recovery failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 