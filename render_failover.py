#!/usr/bin/env python3
"""
Render-specific failover utilities
Since Render doesn't support direct service manipulation, 
this module provides helper functions for failover scenarios
"""

import os
import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class RenderFailover:
    def __init__(self):
        self.render_api_key = os.getenv("RENDER_API_KEY")
        self.render_api_base = "https://api.render.com/v1"
        
    def get_service_info(self, service_name: str) -> Optional[Dict]:
        """Get information about a Render service"""
        if not self.render_api_key:
            logger.warning("No Render API key configured")
            return None
            
        try:
            headers = {
                "Authorization": f"Bearer {self.render_api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.render_api_base}/services",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                services = response.json()
                for service in services.get("services", []):
                    if service.get("name") == service_name:
                        return service
            else:
                logger.error(f"Failed to get service info: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error getting service info: {e}")
            
        return None
    
    def restart_service(self, service_name: str) -> bool:
        """Restart a Render service"""
        if not self.render_api_key:
            logger.warning("No Render API key configured")
            return False
            
        service_info = self.get_service_info(service_name)
        if not service_info:
            logger.error(f"Service {service_name} not found")
            return False
            
        try:
            headers = {
                "Authorization": f"Bearer {self.render_api_key}",
                "Content-Type": "application/json"
            }
            
            service_id = service_info["id"]
            response = requests.post(
                f"{self.render_api_base}/services/{service_id}/deploys",
                headers=headers,
                json={"clearCache": False},
                timeout=10
            )
            
            if response.status_code == 201:
                logger.info(f"Service {service_name} restart initiated")
                return True
            else:
                logger.error(f"Failed to restart service: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error restarting service: {e}")
            return False
    
    def get_service_logs(self, service_name: str, lines: int = 100) -> Optional[str]:
        """Get recent logs from a Render service"""
        if not self.render_api_key:
            logger.warning("No Render API key configured")
            return None
            
        service_info = self.get_service_info(service_name)
        if not service_info:
            logger.error(f"Service {service_name} not found")
            return None
            
        try:
            headers = {
                "Authorization": f"Bearer {self.render_api_key}",
                "Content-Type": "application/json"
            }
            
            service_id = service_info["id"]
            response = requests.get(
                f"{self.render_api_base}/services/{service_id}/logs",
                headers=headers,
                params={"limit": lines},
                timeout=10
            )
            
            if response.status_code == 200:
                logs = response.json()
                return "\n".join([log.get("message", "") for log in logs.get("logs", [])])
            else:
                logger.error(f"Failed to get logs: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return None
    
    def notify_failover_event(self, event_type: str, details: Dict) -> bool:
        """Send failover event notification"""
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return False
            
        try:
            payload = {
                "text": f"ChromaDB Failover Event: {event_type}",
                "attachments": [
                    {
                        "color": "#ff9500",
                        "fields": [
                            {
                                "title": "Event Type",
                                "value": event_type,
                                "short": True
                            },
                            {
                                "title": "Details",
                                "value": str(details),
                                "short": False
                            }
                        ]
                    }
                ]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False 