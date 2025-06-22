# 🚨 USE CASE 2 Testing - READ THIS FIRST

## ⚠️ CRITICAL: Manual Testing Required

**USE CASE 2 (Primary Instance Down) testing requires MANUAL primary instance suspension.**

### 🚫 **DON'T Do This**
```bash
# ❌ This gives false results for USE CASE 2
python run_enhanced_tests.py --url https://chroma-load-balancer.onrender.com
```

### ✅ **DO This Instead**
```bash
# 1. Suspend primary instance via Render dashboard
# 2. Wait 30-60 seconds  
# 3. Run manual testing:
python use_case_2_manual_testing.py --manual-confirmed
```

### 📋 **Quick Steps**
1. **Go to Render dashboard** → `chroma-primary` → **Suspend**
2. **Wait 30-60 seconds** for health detection
3. **Run manual test**: `python use_case_2_manual_testing.py --manual-confirmed`
4. **Resume primary** via Render dashboard after testing

### 📚 **Full Documentation**
- **Complete protocol**: `USE_CASE_2_TESTING_PROTOCOL.md`
- **Production use cases**: `USE_CASES.md`

**The automated test suite will redirect you here if you try to run USE CASE 2 tests incorrectly.** 