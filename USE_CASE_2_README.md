# 🚨 USE CASE 2 Testing - READ THIS FIRST

## ⭐ **ENHANCED TESTING SCRIPT AVAILABLE**

**USE CASE 2 (Primary Instance Down) testing now has a comprehensive guided script with selective cleanup.**

### ✅ **RECOMMENDED: Enhanced Guided Testing**
```bash
# Complete guided testing with automatic cleanup
python test_use_case_2_manual.py --url https://chroma-load-balancer.onrender.com
```

**The enhanced script provides:**
- **Step-by-step guidance** for manual primary suspension via Render dashboard
- **4 automated tests** during infrastructure failure (collection creation, document addition with embeddings, document query, additional collection)
- **Automatic monitoring** of primary recovery and sync completion
- **Selective cleanup** - same as USE CASE 1: removes successful test data, preserves failed test data for debugging
- **Complete testing summary** with success metrics

### 🚫 **DON'T Do This**
```bash
# ❌ This gives false results for USE CASE 2
python run_enhanced_tests.py --url https://chroma-load-balancer.onrender.com
```

### 📋 **Quick Steps**
1. **Run the enhanced script**: `python test_use_case_2_manual.py --url https://chroma-load-balancer.onrender.com`
2. **Follow guided prompts** for primary suspension via Render dashboard
3. **Script handles all testing** during infrastructure failure automatically
4. **Follow guided prompts** for primary recovery
5. **Automatic cleanup** removes successful test data

### 📚 **Full Documentation**
- **Complete use cases**: `USE_CASES.md` (fully updated)
- **Production deployment**: `PRODUCTION_TESTING_GUIDE.md`

**The enhanced script provides enterprise-grade infrastructure failure testing with bulletproof data protection.** 