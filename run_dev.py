#!/usr/bin/env python3
"""
Development runner for BLASST Controller
Launches the app directly for testing without building
"""

import sys
import os
from blasst_app_main import main

if __name__ == "__main__":
    # Make sure we're in the correct directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    try:
        print("Running BLASST Controller in development mode")
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nApplication terminated by user")
    except Exception as e:
        print(f"\nError in main application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 