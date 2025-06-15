#!/usr/bin/env python3
"""
Quick fix to add Flask import to unified_wal_load_balancer.py
"""

import os

def fix_flask_import():
    """Add Flask import to the top of unified_wal_load_balancer.py"""
    
    file_path = "unified_wal_load_balancer.py"
    
    # Read the current file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Check if Flask is already imported at the top
    if "from flask import Flask" in content[:1000]:  # Check first 1000 chars
        print("✅ Flask already imported at top")
        return True
    
    # Find the imports section and add Flask
    import_section = """import os
import sys
import time
import logging
import requests
import threading
import random
import json
import uuid
import psycopg2
import psycopg2.extras
import psutil
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc"""
    
    flask_import_section = """import os
import sys
import time
import logging
import requests
import threading
import random
import json
import uuid
import psycopg2
import psycopg2.extras
import psutil
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc

# Flask imports for web service
from flask import Flask, request, Response, jsonify"""
    
    # Replace the import section
    if import_section in content:
        content = content.replace(import_section, flask_import_section)
        print("✅ Added Flask import to top of file")
    else:
        print("❌ Could not find import section")
        return False
    
    # Remove duplicate Flask import from main block
    content = content.replace(
        "        # Initialize Flask app for web service\n        from flask import Flask, request, Response, jsonify\n        app = Flask(__name__)",
        "        # Initialize Flask app for web service (Flask imported at top)\n        app = Flask(__name__)"
    )
    
    # Write the fixed file
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("✅ Flask import fix applied successfully")
    return True

if __name__ == "__main__":
    fix_flask_import() 