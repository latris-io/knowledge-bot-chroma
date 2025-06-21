# ChromaDB Codebase Cleanup Plan

## 🎯 ESSENTIAL FILES TO KEEP (20 files)

### Core Production Files
- `unified_wal_load_balancer.py` - Main production service
- `Dockerfile.loadbalancer` - Container setup
- `render.yaml` - Deployment config
- `startup.sh` - Service startup
- `requirements.txt` - Dependencies

### Production Tests (Keep 2 main test suites)
- `run_all_tests.py` - Production validation tests
- `run_enhanced_tests.py` - Enhanced test suite with use cases
- `enhanced_test_base_cleanup.py` - Test infrastructure

### Essential Cleanup/Monitoring
- `comprehensive_system_cleanup.py` - Production data cleanup
- `comprehensive_resource_monitor.py` - Resource monitoring

### Documentation
- `USE_CASES.md` - Production requirements doc
- `README.md` (if exists)

### Database Schemas
- `*.sql` files for schemas

## 🗑️ FILES TO DELETE (80+ files)

### Temporary Fix Files (DELETE ALL)
- `fix_*.py` (20+ files) - All temporary diagnostic scripts
- `debug_*.py` (10+ files) - All debug scripts  
- `quick_*.py` - All quick fix attempts

### Redundant Test Files (DELETE MOST)
- `test_*.py` (30+ files) - Keep only core tests, delete redundant ones
- `enhanced_test_*_original.py` - Old versions
- `enhanced_test_*_upgraded.py` - Duplicate versions
- `investigate_*.py` - Investigation scripts

### Backup/Broken Files (DELETE ALL)
- `unified_wal_load_balancer.py.bak` - Backup file
- `unified_wal_load_balancer.py.broken` - Broken version
- `*.bak` files

### Check/Monitor Scripts (DELETE REDUNDANT)
- `check_*.py` (15+ files) - Most are redundant
- `analyze_*.py` - Analysis scripts

### Deployment Utilities (DELETE REDUNDANT)
- Multiple deployment scripts
- Duplicate monitoring files

## 📊 SUMMARY
- Current: 99+ files
- Target: ~20 essential files  
- Cleanup: Remove ~80 temporary/duplicate files 