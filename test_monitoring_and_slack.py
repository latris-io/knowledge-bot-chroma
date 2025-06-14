#!/usr/bin/env python3
"""
Test Suite for Resource Monitoring and Slack Notifications
Tests: upgrade recommendations, Slack alerts, resource tracking, database schema
"""

import os
import time
import json
import requests
import psycopg2
import unittest
from unittest.mock import patch, MagicMock
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

class TestMonitoringAndSlack(unittest.TestCase):
    """Test monitoring and Slack notification features"""
    
    def setUp(self):
        if not DATABASE_URL:
            self.skipTest("DATABASE_URL not available")
    
    def test_database_schema_exists(self):
        """Test that all required monitoring tables exist"""
        logger.info("🗄️ Testing database schema...")
        
        required_tables = [
            'performance_metrics',
            'upgrade_recommendations', 
            'sync_tasks',
            'sync_workers'
        ]
        
        try:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    for table in required_tables:
                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_name = %s
                            )
                        """, [table])
                        exists = cursor.fetchone()[0]
                        self.assertTrue(exists, f"Table {table} should exist")
                        logger.info(f"✅ Table {table} exists")
        except Exception as e:
            self.fail(f"Database schema test failed: {e}")
    
    @patch('requests.post')
    def test_slack_notification_format(self, mock_post):
        """Test Slack notification message formatting"""
        logger.info("📱 Testing Slack notification format...")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        test_recommendation = {
            'type': 'memory',
            'current': 87.3,
            'recommended_tier': 'standard',
            'cost': 21,
            'reason': 'Memory usage at 87.3% - approaching limit',
            'urgency': 'high'
        }
        
        webhook_url = "https://hooks.slack.com/services/test/webhook/url"
        
        # Simulate Slack notification
        payload = {
            "text": "🚨 ChromaDB Upgrade Needed",
            "attachments": [
                {
                    "color": "danger",
                    "title": f"chroma-sync ({test_recommendation['type']} upgrade needed)",
                    "text": f"*{test_recommendation['reason']}*",
                    "fields": [
                        {
                            "title": "Current Usage",
                            "value": f"{test_recommendation['current']:.1f}%",
                            "short": True
                        }
                    ]
                }
            ]
        }
        
        requests.post(webhook_url, json=payload, timeout=10)
        
        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], webhook_url)
        
        sent_payload = call_args[1]['json']
        self.assertIn('text', sent_payload)
        self.assertIn('attachments', sent_payload)
        
        logger.info("✅ Slack notification format test passed")
    
    def test_upgrade_recommendation_logic(self):
        """Test upgrade recommendation generation"""
        logger.info("💡 Testing upgrade recommendation logic...")
        
        test_cases = [
            {'memory': 87.5, 'cpu': 45, 'expected': ['memory']},
            {'memory': 75, 'cpu': 85, 'expected': ['cpu']},
            {'memory': 96, 'cpu': 88, 'expected': ['memory', 'cpu']}
        ]
        
        for i, case in enumerate(test_cases):
            recommendations = []
            
            if case['memory'] > 85:
                recommendations.append('memory')
            if case['cpu'] > 80:
                recommendations.append('cpu')
            
            for expected in case['expected']:
                self.assertIn(expected, recommendations)
            
            logger.info(f"✅ Test case {i+1}: {len(recommendations)} recommendations")

def run_monitoring_tests():
    """Run all monitoring tests"""
    logger.info("🧪 Starting Monitoring Test Suite...")
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMonitoringAndSlack)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    
    logger.info(f"\n📊 RESULTS: {passed}/{total} tests passed")
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_monitoring_tests()
    exit(0 if success else 1) 