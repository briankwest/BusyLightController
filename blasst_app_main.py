#!/usr/bin/env python3

import sys
from blasst_app import main

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("Application terminated by user")
    except Exception as e:
        print(f"Error in main application: {e}")
        sys.exit(1) 