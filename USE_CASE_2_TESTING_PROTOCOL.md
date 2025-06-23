# 🚨 USE CASE 2 Testing Protocol - ENHANCED SCRIPT AVAILABLE

## ⭐ **UPDATED: Enhanced Testing Script with Guided Experience**

**This document has been updated to reflect the current enhanced testing approach.**

### 🎯 **Current Recommended Approach**

**USE CASE 2 (Primary Instance Down) testing now uses an enhanced guided script:**

```bash
# Enhanced testing with guided prompts and selective cleanup
python test_use_case_2_manual.py --url https://chroma-load-balancer.onrender.com
```

## 🚀 **Enhanced Script Features**

### **✅ Complete Guided Experience**
- **Step-by-step prompts** for manual primary suspension via Render dashboard
- **Clear instructions** at each stage with specific actions to take
- **Built-in verification** that proper steps have been followed
- **Automatic monitoring** of system health and recovery

### **✅ Automated Testing During Failure**
The script automatically runs **4 comprehensive tests** during primary failure:
1. **Collection Creation** - Creates test collection during infrastructure failure
2. **Document Addition** - Adds document with embeddings during failure  
3. **Document Query** - Queries documents using embeddings during failure
4. **Additional Collection** - Creates second test collection during failure

### **✅ Enhanced Recovery and Sync**
- **Automatic monitoring** of primary recovery detection
- **WAL sync verification** with timeout handling
- **Data consistency validation** across both instances
- **Complete testing summary** with success metrics

### **✅ Selective Cleanup (Same as USE CASE 1)**
- **Preserves failed test data** for debugging with collection URLs
- **Removes successful test data** automatically 
- **Bulletproof production protection** (global collection safety)
- **Enhanced debugging information** for preserved collections

## 📋 **Testing Flow**

### **1. Script Launch**
```bash
python test_use_case_2_manual.py --url https://chroma-load-balancer.onrender.com
```

### **2. Guided Primary Suspension**
The script provides clear instructions:
```
🔴 MANUAL ACTION REQUIRED: Suspend Primary Instance

1. Go to your Render dashboard (https://dashboard.render.com)
2. Navigate to 'chroma-primary' service
3. Click 'Suspend' to simulate infrastructure failure
4. Wait 5-10 seconds for health detection to update

Press Enter when ready to continue...
```

### **3. Automated Failure Testing**
The script automatically:
- Verifies primary failure detection
- Runs 4 comprehensive operation tests
- Validates all operations work during infrastructure failure
- Provides real-time success/failure feedback

### **4. Guided Primary Recovery**
The script provides recovery instructions:
```
🔴 MANUAL ACTION REQUIRED: Resume Primary Instance

1. Go back to your Render dashboard
2. Navigate to 'chroma-primary' service  
3. Click 'Resume' or 'Restart' to restore the primary
4. Wait for the service to fully start up (~30-60 seconds)

Press Enter when ready to continue...
```

### **5. Automatic Sync Verification**
The script automatically:
- Monitors primary recovery detection
- Waits for WAL sync completion
- Verifies data consistency across instances
- Provides comprehensive testing summary

### **6. Selective Cleanup**
The script automatically:
- Analyzes which tests passed vs failed
- Removes collections from successful tests only
- Preserves failed test data with debugging URLs
- Provides cleanup summary

## 🛡️ **Built-in Safeguards**

### **Enhanced Safety Features**
- **Health verification** before starting tests
- **Manual confirmation prompts** at each critical step
- **Automatic failure detection** and reporting
- **Bulletproof production data protection**

### **Error Handling**
- **Graceful timeout handling** for network issues
- **Clear error messages** with debugging guidance
- **Selective data preservation** for failed tests
- **Emergency cleanup capabilities**

## 🚫 **What NOT To Do**

### **❌ DON'T Use Automated Scripts for Real Infrastructure Testing**
```bash
# This only tests failover logic, not real infrastructure failure
python run_enhanced_tests.py --url https://chroma-load-balancer.onrender.com
```

### **❌ DON'T Skip the Enhanced Script**
The enhanced script provides critical features:
- Guided manual steps reduce errors
- Automated testing ensures comprehensive coverage
- Selective cleanup prevents data pollution
- Complete lifecycle management

## 📊 **Expected Results**

### **Successful Testing Output**
```
📊 USE CASE 2 TESTING SUMMARY
================================
⏱️  Total test time: 8.5 minutes
🧪 Operations during failure: 4/4 successful (100.0%)
🔄 Primary recovery: ✅ Success
📊 Data consistency: ✅ Complete
🧹 Automatic cleanup: ✅ Complete

🎉 USE CASE 2: ✅ SUCCESS - Enterprise-grade high availability validated!
   Your system maintains CMS operations during infrastructure failures.
```

### **Performance Metrics**
- **Operation Response Times**: 0.6-1.1 seconds during infrastructure failure
- **Zero Transaction Loss**: All operations complete successfully
- **Recovery Time**: Primary restoration detected in ~5 seconds
- **Sync Completion**: WAL sync completes within 1-2 minutes

## 📚 **Documentation References**

### **Complete Documentation**
- **USE_CASES.md**: Complete use case documentation with current enhanced script details
- **PRODUCTION_TESTING_GUIDE.md**: Production-safe testing with enhanced cleanup
- **TESTING_GUIDE.md**: Comprehensive testing approaches

### **Related Scripts**
- **test_use_case_2_manual.py**: Current enhanced testing script (RECOMMENDED)
- **run_all_tests.py**: Production validation with selective cleanup (USE CASE 1)
- **comprehensive_system_cleanup.py**: Emergency cleanup if needed

## 🎯 **Why This Approach Works**

### **Enterprise-Grade Testing**
- **Real infrastructure failure simulation** via Render dashboard suspension
- **Comprehensive operation coverage** during actual outages
- **Complete recovery validation** with data consistency verification
- **Production-safe cleanup** with intelligent data preservation

### **User Experience**
- **Guided prompts** eliminate guesswork and errors
- **Automatic monitoring** provides real-time feedback
- **Clear success/failure indicators** at each stage
- **Complete testing summary** with actionable results

**The enhanced script provides the same professional testing experience as USE CASE 1 while handling the complexity of manual infrastructure failure simulation.** 