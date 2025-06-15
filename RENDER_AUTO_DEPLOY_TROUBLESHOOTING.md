# Render Auto-Deploy Troubleshooting Guide

## 🔍 **Issue: chroma-load-balancer No Longer Auto-Deploys**

Your `chroma-load-balancer` service has stopped automatically deploying when you push to GitHub. Here's how to diagnose and fix this issue.

## ✅ **Current Status Check**

All required files are present and correct:
- ✅ `render.yaml` - contains chroma-load-balancer service definition
- ✅ `Dockerfile.loadbalancer` - Docker build configuration  
- ✅ `stable_load_balancer.py` - main Flask application
- ✅ `requirements.loadbalancer.txt` - Python dependencies
- ✅ Recent GitHub commits are successful

## 🎯 **Most Likely Causes & Solutions**

### 1. **Auto-Deploy Disabled in Render Dashboard** (Most Common)

**Check:**
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Navigate to `chroma-load-balancer` service
3. Click **Settings** tab
4. Look for **Auto-Deploy** setting

**Fix:**
- If Auto-Deploy is **OFF**: Toggle it **ON**
- If it's already ON: Toggle OFF, save, then toggle ON again

### 2. **GitHub Integration Broken**

**Check:**
1. In Render service settings, verify **Repository** is correctly connected
2. Check that **Branch** is set to `main` (not `master` or other)
3. Verify GitHub webhook is active

**Fix:**
1. **Reconnect Repository:**
   - Settings → Repository → Disconnect
   - Reconnect and reauthorize GitHub access
2. **Verify Branch:**
   - Ensure branch is set to `main`
   - Check that `main` is your default branch in GitHub

### 3. **Previous Build Failures**

**Check:**
1. Go to **Deploys** tab in Render dashboard
2. Look for failed deployments (red X marks)
3. Check build logs for errors

**Common Build Errors:**
```bash
# Docker build failed
ERROR: failed to solve: failed to compute cache key

# Missing dependencies  
ERROR: Could not find a version that satisfies the requirement

# Port binding issues
ERROR: Port 8000 is already in use
```

**Fix:**
- **Manual Deploy:** Click "Deploy Latest Commit" to retry
- **Fix Build Errors:** Address specific errors in logs
- **Clear Build Cache:** Sometimes helps with Docker issues

### 4. **Resource/Billing Issues**

**Check:**
1. Render Dashboard → Account → Billing
2. Verify your plan hasn't exceeded limits
3. Check if service is suspended

**Fix:**
- Upgrade plan if needed
- Pay any outstanding bills
- Contact Render support if suspended

### 5. **GitHub Webhook Issues**

**Check:**
1. GitHub Repository → Settings → Webhooks
2. Look for Render webhook (usually ends with `render.com`)
3. Check recent deliveries for failures

**Fix:**
1. **Regenerate Webhook:**
   - Delete existing Render webhook in GitHub
   - In Render: Disconnect and reconnect repository
   - This creates a fresh webhook

### 6. **File Path or Dockerfile Issues**

**Check:**
- Verify `Dockerfile.loadbalancer` is in repository root
- Check for typos in file names
- Ensure all referenced files exist

## 🛠️ **Step-by-Step Fix Procedure**

### Step 1: Quick Dashboard Check
```
1. Open Render Dashboard
2. Go to chroma-load-balancer service  
3. Settings tab → Auto-Deploy should be ON
4. Repository should show your GitHub repo
5. Branch should be 'main'
```

### Step 2: Manual Deploy Test
```
1. Deploys tab → "Deploy Latest Commit"
2. Watch build logs for errors
3. If successful: Auto-deploy should resume
4. If failed: Fix errors from logs
```

### Step 3: Repository Reconnection (if needed)
```
1. Settings tab → Repository section
2. Click "Disconnect"
3. Click "Connect Repository" 
4. Reauthorize GitHub access
5. Select correct repository and branch
```

### Step 4: GitHub Webhook Verification
```
1. GitHub repo → Settings → Webhooks
2. Find Render webhook (check Recent Deliveries)
3. If failing: Delete webhook
4. Render will recreate it automatically
```

## 🔧 **Manual Deploy Commands**

If you need to force a deployment while troubleshooting:

```bash
# Option 1: Push empty commit to trigger deploy
git commit --allow-empty -m "Trigger deployment"
git push origin main

# Option 2: Use Render CLI (if installed)
render deploy --service chroma-load-balancer
```

## 📊 **Common Error Messages & Fixes**

| Error Message | Cause | Fix |
|---------------|-------|-----|
| "Build failed: No such file" | Missing Dockerfile | Check file paths |
| "Repository not found" | GitHub permission issue | Reconnect repository |
| "Auto-deploy is disabled" | Setting turned off | Enable in dashboard |
| "Webhook delivery failed" | GitHub webhook broken | Regenerate webhook |
| "Build timeout" | Resource limits | Upgrade plan |

## 🆘 **When All Else Fails**

### Nuclear Option: Complete Service Recreation
```
1. Note down all environment variables
2. Delete chroma-load-balancer service
3. Create new service with same configuration
4. This creates fresh GitHub integration
```

### Contact Render Support
- **Dashboard:** Help & Support section
- **Email:** Include service name and recent deploy logs
- **GitHub Issue:** Sometimes deployment issues are platform-wide

## ✅ **Prevention Tips**

1. **Regular Monitoring:** Check deploy logs occasionally
2. **Webhook Health:** Monitor GitHub webhook deliveries
3. **Branch Protection:** Ensure `main` branch is your deploy target
4. **Build Testing:** Test Docker builds locally before pushing
5. **Resource Monitoring:** Keep an eye on plan limits

## 🎯 **Next Steps**

1. **Check Render Dashboard** first (most likely cause)
2. **Test manual deployment** to verify service is working
3. **Reconnect repository** if auto-deploy setting is correct
4. **Check GitHub webhooks** if reconnection doesn't work
5. **Contact Render support** if issue persists

Most auto-deploy issues are resolved by steps 1-3. The key is methodically checking each potential cause rather than guessing! 