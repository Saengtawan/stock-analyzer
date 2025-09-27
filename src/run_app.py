#!/usr/bin/env python3
"""
Web application runner with proper path setup
"""
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Run Flask app')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    args = parser.parse_args()

    from web.app import app
    app.run(debug=True, host='0.0.0.0', port=args.port)