#!/usr/bin/env python3
"""
Run just the document operations test from the main test suite
"""

from run_all_tests import UnifiedWALTestSuite

def test_just_documents():
    print("🧪 Running ONLY Document Operations Test from Main Test Suite...")
    print("=" * 60)
    
    suite = UnifiedWALTestSuite()
    
    # Run just the document operations test
    try:
        result = suite.test_document_operations()
        
        if result:
            print("📊 Document Operations Result: ✅ SUCCESS")
            print("🎉 Document operations are working with the existing embeddings!")
        else:
            print("📊 Document Operations Result: ❌ FAILED")
            print("⚠️ There may be infrastructure issues causing failures")
            
        # Show individual test results
        print("\n📋 Individual Test Results:")
        for test_result in suite.results:
            status = "✅" if test_result['success'] else "❌"
            print(f"   {status} {test_result['test_name']}: {test_result['details']}")
            
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
    
    # Cleanup
    try:
        suite.comprehensive_cleanup()
    except:
        pass

if __name__ == "__main__":
    test_just_documents() 