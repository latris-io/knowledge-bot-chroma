# Adding Slack Notifications for Upgrade Alerts
## Get notified when you need to upgrade services

### 🎯 **Quick Setup (5 minutes)**

Currently you get upgrade notifications in **logs only**. Here's how to add **Slack alerts**:

---

## 📱 **Step 1: Get Slack Webhook URL**

1. Go to your Slack workspace
2. Click **Apps** → **Browse Apps** 
3. Search **"Incoming Webhooks"** → **Add to Slack**
4. Choose channel (e.g., `#infrastructure-alerts`)
5. Copy the webhook URL (looks like: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX`)

---

## ⚙️ **Step 2: Add to Render Dashboard**

1. Go to **Render Dashboard**
2. Click **chroma-monitor** service
3. Go to **Environment** tab
4. Find **SLACK_WEBHOOK_URL** 
5. Paste your webhook URL
6. Click **Save Changes**

**Services will auto-restart with Slack enabled!**

---

## 🚨 **What You'll Get in Slack**

### **Infrastructure Alerts:**
```
🚨 ChromaDB Alert - High Priority 
Service: chroma-sync
Issue: Memory usage at 87.3% - approaching limit
Recommendation: Upgrade to Standard plan ($21/month)
Time: 2024-01-15 10:30:45 UTC
```

### **Performance Warnings:**
```
⚠️ ChromaDB Performance Warning
Service: chroma-sync  
Issue: Sync duration 12.4 minutes - performance degraded
Recommendation: Consider CPU upgrade
Time: 2024-01-15 10:35:12 UTC
```

### **Service Health Issues:**
```
❌ ChromaDB Service Down
Primary: ❌ Not responding
Replica: ✅ Healthy  
Load Balancer: Switched to replica-only mode
Action Required: Check primary service logs
```

---

## 📊 **Notification Frequency**

### **Upgrade Recommendations:**
- 🔴 **Critical (>95% resource)**: Immediate alert + every hour until fixed
- 🟡 **Warning (>85% resource)**: Once daily until addressed  
- 🟢 **Advisory (>75% resource)**: Once weekly for trend awareness

### **Service Health:**
- 🚨 **Service down**: Immediate alert
- ⚠️ **Degraded performance**: Every 30 minutes
- ✅ **Recovery**: Single "all clear" message

---

## 🎛️ **Advanced: Custom Slack Channels**

You can set different webhook URLs for different alert types:

### **For Critical Infrastructure Alerts:**
```bash
# Set in chroma-monitor service:
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/.../infrastructure-critical
```

### **For Performance Warnings:**
```bash  
# Set in chroma-sync service (if you want separate channel):
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/.../performance-alerts
```

---

## 🔧 **Option 2: Enhanced Sync Service Notifications**

If you want **more detailed** upgrade notifications from the sync service itself:

### **Add to data_sync_service.py:**
```python
def send_slack_notification(self, message: str, urgency: str = "medium"):
    """Send Slack notification for upgrade recommendations"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    
    emoji = "🚨" if urgency == "high" else "⚠️" if urgency == "medium" else "ℹ️"
    
    payload = {
        "text": f"{emoji} ChromaDB Sync Alert",
        "attachments": [
            {
                "color": "danger" if urgency == "high" else "warning",
                "text": message,
                "footer": "ChromaDB Monitoring",
                "ts": int(time.time())
            }
        ]
    }
    
    try:
        requests.post(webhook_url, json=payload)
    except Exception as e:
        logger.debug(f"Failed to send Slack notification: {e}")

# Then modify the upgrade check:
def check_upgrade_recommendations(self, metrics: ResourceMetrics):
    # ... existing code ...
    
    # Send Slack for urgent recommendations
    urgent_recs = [r for r in recommendations if r['urgency'] == 'high']
    if urgent_recs:
        message = f"URGENT: {urgent_recs[0]['reason']}\nRecommended: {urgent_recs[0]['recommended_tier']} plan (${urgent_recs[0]['cost']}/month)"
        self.send_slack_notification(message, "high")
        logger.warning(f"🚨 URGENT: Resource upgrade recommended - {urgent_recs[0]['reason']}")
```

---

## 🎯 **Recommended Setup**

### **For Most Users (Simple):**
1. ✅ Set `SLACK_WEBHOOK_URL` on **chroma-monitor** service
2. ✅ Get alerts for service health + basic upgrade needs
3. ✅ Check Render logs for detailed upgrade recommendations

### **For Power Users (Advanced):**
1. ✅ Add custom Slack code to sync service
2. ✅ Get detailed upgrade notifications with cost estimates
3. ✅ Separate channels for different alert types

---

## 💡 **Pro Tips**

### **Slack Channel Naming:**
- `#chroma-critical` - Service outages, urgent upgrades
- `#chroma-performance` - Sync issues, memory warnings
- `#chroma-info` - General status, successful deployments

### **Alert Tuning:**
```python
# Customize thresholds in data_sync_service.py:
memory_warning_threshold = 85  # Default: warn at 85%
memory_critical_threshold = 95  # Default: urgent at 95%
sync_slow_threshold = 600      # Default: warn if sync > 10 minutes
```

### **Quiet Hours:**
```python
# Don't send non-critical alerts at night:
import datetime
now = datetime.datetime.now()
if 23 <= now.hour or now.hour <= 6:  # 11 PM to 6 AM
    if urgency != "high":
        return  # Skip non-urgent notifications during quiet hours
```

---

## 🎉 **Result**

After setup, you'll get **proactive Slack notifications** for:
- ✅ When to upgrade each service (with cost estimates)  
- ✅ Service health issues (outages, performance problems)
- ✅ Trend analysis (gradual resource growth patterns)
- ✅ Recovery confirmations (when issues are resolved)

**Never miss an upgrade opportunity or service issue again!** 📱⚡ 