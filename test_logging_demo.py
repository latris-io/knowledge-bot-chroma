#!/usr/bin/env python3
"""
Logging Demo Script
Demonstrates the new persistent logging system for debugging
"""

import time
import requests
from logging_config import setup_test_logging, log_error_details, log_system_status

def main():
    print("🔍 LOGGING SYSTEM DEMONSTRATION")
    print("=" * 50)
    
    # Set up logging for this demo
    logger = setup_test_logging("logging_demo")
    
    print("1. Testing basic logging...")
    logger.info("Demo script started")
    logger.debug("This is a debug message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    
    print("2. Testing system status logging...")
    mock_status = {
        "healthy_instances": 2,
        "total_instances": 2,
        "write_ahead_log": {
            "pending_writes": 0,
            "total_replayed": 15,
            "failed_replays": 0
        },
        "instances": [
            {"name": "primary", "healthy": True},
            {"name": "replica", "healthy": False}  # Simulating failure
        ]
    }
    log_system_status("logging_demo", mock_status)
    
    print("3. Testing error logging...")
    try:
        # Simulate an error
        raise Exception("Simulated test failure for logging demo")
    except Exception as e:
        log_error_details("logging_demo", e, {
            "test_context": "logging_demonstration",
            "simulated": True,
            "timestamp": time.time()
        })
    
    print("4. Testing real API call with logging...")
    try:
        # Try to make a real API call (will likely fail, but that's OK for demo)
        url = "https://chroma-load-balancer.onrender.com/status"
        logger.info(f"Attempting API call to {url}")
        
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"API call successful: {response.status_code}")
            log_system_status("logging_demo", {
                "api_response": response.json(),
                "response_time_ms": response.elapsed.total_seconds() * 1000
            })
        else:
            logger.warning(f"API call failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"API call exception: {e}")
        log_error_details("logging_demo", e, {"api_url": url})
    
    logger.info("Demo completed successfully")
    
    print("\n✅ LOGGING DEMO COMPLETED!")
    print("\nCheck these files for persistent logs:")
    print("- logs/system.log (master log with all components)")
    print("- logs/test_logging_demo_*.log (this test's main log)")
    print("- logs/tests/logging_demo_*.log (timestamped test log)")
    print("- logs/logging_demo_status.log (system status logs)")
    print("- logs/logging_demo_errors.log (error details)")
    
    print("\n🎯 Now when tests hang or fail, you'll have detailed logs to examine!")

if __name__ == "__main__":
    main() 