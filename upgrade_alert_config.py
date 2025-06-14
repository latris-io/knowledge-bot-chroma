#!/usr/bin/env python3
"""
Upgrade Alert Configuration
Defines when monitoring system should alert about resource constraints
"""

# Resource monitoring thresholds and upgrade recommendations
UPGRADE_THRESHOLDS = {
    # Memory thresholds
    "memory": {
        "warning": 80,    # 80% - yellow alert
        "critical": 95,   # 95% - red alert, immediate upgrade needed
        "upgrade_cost": {
            "standard": 21,     # Standard plan: +$21/month
            "professional": 85  # Professional plan: +$85/month
        }
    },
    
    # CPU thresholds  
    "cpu": {
        "warning": 80,     # 80% - performance degradation
        "critical": 95,    # 95% - service instability  
        "upgrade_cost": {
            "standard": 21,     # Standard plan: +$21/month
            "professional": 85  # Professional plan: +$85/month
        }
    },
    
    # Disk thresholds
    "disk": {
        "warning": 80,     # 80% - plan storage expansion
        "critical": 90,    # 90% - urgent expansion needed
        "upgrade_cost": {
            "25gb": 10,        # 25GB disk: +$10/month
            "50gb": 20,        # 50GB disk: +$20/month
            "100gb": 35        # 100GB disk: +$35/month
        }
    }
}

# Performance-based upgrade triggers
PERFORMANCE_THRESHOLDS = {
    "concurrent_users": {
        "current_capacity": 8,      # Current max with optimizations
        "error_rate_threshold": 25, # 25% error rate triggers upgrade alert
        "response_time_threshold": 5, # 5+ second responses
        "next_tier_capacity": 20,   # Expected capacity after upgrade
        "upgrade_cost": 77          # Full upgrade cost for 20 users
    },
    
    "load_balancer": {
        "throttling_rate_threshold": 10,  # 10% requests throttled
        "circuit_breaker_trips": 5,       # 5+ circuit breaker trips per hour
        "connection_pool_exhaustion": 80, # 80% pool usage
        "upgrade_recommendation": "standard_plan"
    },
    
    "sync_service": {
        "sync_lag_threshold": 600,    # 10+ minutes sync lag
        "memory_pressure_threshold": 85, # 85% memory during sync
        "batch_failure_rate": 15,     # 15% batch failures
        "upgrade_priority": "high"    # Usually first to need upgrade
    }
}

# Alert frequency limits (prevent spam)
ALERT_COOLDOWNS = {
    "memory_warning": 3600,      # 1 hour between memory warnings
    "memory_critical": 1800,     # 30 minutes between critical alerts
    "cpu_warning": 3600,         # 1 hour between CPU warnings
    "cpu_critical": 1800,        # 30 minutes between critical alerts
    "disk_warning": 21600,       # 6 hours between disk warnings
    "performance_degradation": 7200, # 2 hours between performance alerts
    "upgrade_recommendation": 21600  # 6 hours between upgrade recommendations
}

# Slack notification templates
SLACK_MESSAGES = {
    "memory_warning": {
        "color": "#ffcc00",
        "title": "Memory Usage Warning",
        "template": "🟡 Memory usage at {usage}% on {service_name}\n"
                   "• Current: {usage}%\n"
                   "• Threshold: {threshold}%\n"
                   "• Recommendation: Monitor closely, upgrade may be needed soon\n"
                   "• Estimated upgrade cost: +${cost}/month"
    },
    
    "memory_critical": {
        "color": "#ff0000", 
        "title": "CRITICAL: Memory Usage",
        "template": "🔴 CRITICAL: Memory usage at {usage}% on {service_name}\n"
                   "• Current: {usage}%\n"
                   "• Threshold: {threshold}%\n"
                   "• Action Required: Upgrade to Standard plan immediately\n"
                   "• Cost: +${cost}/month\n"
                   "• Risk: Service instability, potential downtime"
    },
    
    "performance_degradation": {
        "color": "#ff6600",
        "title": "Performance Degradation Detected", 
        "template": "⚠️ Performance issues detected:\n"
                   "• Concurrent users: {concurrent_users}\n"
                   "• Error rate: {error_rate}%\n"
                   "• Average response time: {response_time}s\n"
                   "• Recommendation: {recommendation}\n"
                   "• Estimated cost: +${cost}/month"
    },
    
    "upgrade_success": {
        "color": "#00aa00",
        "title": "System Upgraded Successfully",
        "template": "✅ System upgrade completed:\n"
                   "• Service: {service_name}\n"
                   "• New plan: {new_plan}\n"
                   "• Additional cost: +${cost}/month\n"
                   "• Expected improvements: {improvements}"
    }
}

# Expected performance improvements after upgrades
UPGRADE_BENEFITS = {
    "memory_upgrade": {
        "standard": {
            "memory": "2GB RAM (4x increase)",
            "concurrent_users": "15-20 users", 
            "error_rate_improvement": "50% reduction",
            "cost": 21
        },
        "professional": {
            "memory": "8GB RAM (16x increase)",
            "concurrent_users": "50+ users",
            "error_rate_improvement": "80% reduction", 
            "cost": 85
        }
    },
    
    "cpu_upgrade": {
        "standard": {
            "cpu": "Dedicated CPU cores",
            "response_time_improvement": "60% faster",
            "throughput_increase": "3x operations/second",
            "cost": 21
        }
    },
    
    "full_system_upgrade": {
        "cost": 77,
        "benefits": [
            "20+ concurrent users with <10% error rate",
            "Sub-2 second response times",
            "5x throughput improvement", 
            "Circuit breaker stability",
            "Connection pool efficiency"
        ]
    }
}

# Monitoring configuration
MONITORING_CONFIG = {
    "check_interval": 30,        # Check every 30 seconds
    "alert_aggregation_window": 300, # 5-minute alert windows
    "performance_history_retention": 7, # Keep 7 days of metrics
    "upgrade_recommendation_frequency": "daily",
    "cost_analysis_enabled": True,
    "slack_notifications_enabled": True
}

def get_upgrade_recommendation(service_name: str, resource_type: str, current_usage: float) -> dict:
    """Get upgrade recommendation based on current usage"""
    thresholds = UPGRADE_THRESHOLDS.get(resource_type, {})
    
    if current_usage >= thresholds.get("critical", 100):
        urgency = "critical"
        recommended_action = "immediate_upgrade"
    elif current_usage >= thresholds.get("warning", 100):
        urgency = "warning" 
        recommended_action = "plan_upgrade"
    else:
        urgency = "none"
        recommended_action = "monitor"
    
    return {
        "service": service_name,
        "resource": resource_type,
        "current_usage": current_usage,
        "urgency": urgency,
        "action": recommended_action,
        "estimated_cost": thresholds.get("upgrade_cost", {}).get("standard", 0),
        "threshold_warning": thresholds.get("warning", 0),
        "threshold_critical": thresholds.get("critical", 0)
    }

def format_slack_message(alert_type: str, **kwargs) -> dict:
    """Format Slack message for alert type"""
    template_config = SLACK_MESSAGES.get(alert_type, {})
    
    message = template_config.get("template", "Alert: {alert_type}").format(**kwargs)
    
    return {
        "text": f"ChromaDB Resource Alert: {template_config.get('title', alert_type)}",
        "attachments": [
            {
                "color": template_config.get("color", "#333333"),
                "text": message,
                "footer": "ChromaDB Monitoring System",
                "ts": int(time.time())
            }
        ]
    }

if __name__ == "__main__":
    import time
    
    # Example usage
    print("🔍 Upgrade Alert Configuration Loaded")
    print(f"📊 Memory warning threshold: {UPGRADE_THRESHOLDS['memory']['warning']}%")
    print(f"📊 CPU critical threshold: {UPGRADE_THRESHOLDS['cpu']['critical']}%") 
    print(f"💰 Standard plan upgrade cost: ${UPGRADE_THRESHOLDS['memory']['upgrade_cost']['standard']}/month")
    
    # Test recommendation
    recommendation = get_upgrade_recommendation("chroma-sync", "memory", 87)
    print(f"\n📈 Example recommendation: {recommendation}")
    
    # Test Slack message
    message = format_slack_message(
        "memory_warning", 
        service_name="chroma-sync",
        usage=87,
        threshold=80,
        cost=21
    )
    print(f"\n📱 Example Slack message: {message}") 