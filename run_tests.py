#!/usr/bin/env python3
"""
Test runner script for Stock Analyzer
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(command, description):
    """Run a command and handle errors"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False


def check_dependencies():
    """Check if required dependencies are installed"""
    print("🔍 Checking dependencies...")

    required_packages = [
        'pytest',
        'pandas',
        'requests',
        'yfinance',
        'loguru'
    ]

    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} is installed")
        except ImportError:
            print(f"❌ {package} is missing")
            missing_packages.append(package)

    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Run: pip install -r requirements.txt")
        return False

    return True


def check_api_keys():
    """Check API key configuration"""
    print("\n🔑 Checking API key configuration...")

    fmp_key = os.getenv('FMP_API_KEY')
    tiingo_key = os.getenv('TIINGO_API_KEY')

    if fmp_key and fmp_key != 'your_fmp_api_key_here':
        print("✅ FMP API key is configured")
    else:
        print("⚠️  FMP API key not configured (some tests may be skipped)")

    if tiingo_key and tiingo_key != 'your_tiingo_api_key_here':
        print("✅ Tiingo API key is configured")
    else:
        print("⚠️  Tiingo API key not configured (some tests may be skipped)")

    if not (fmp_key or tiingo_key):
        print("ℹ️  No API keys configured. Only basic tests will run.")

    return True


def run_unit_tests():
    """Run unit tests"""
    command = "python -m pytest tests/ -v -m 'not integration and not slow' --tb=short"
    return run_command(command, "Running unit tests")


def run_integration_tests():
    """Run integration tests"""
    command = "python -m pytest tests/ -v -m 'integration' --tb=short"
    return run_command(command, "Running integration tests")


def run_api_tests():
    """Run API tests (requires API keys)"""
    command = "python -m pytest tests/ -v -m 'api_key_required' --tb=short"
    return run_command(command, "Running API tests (requires API keys)")


def run_all_tests():
    """Run all tests"""
    command = "python -m pytest tests/ -v --tb=short"
    return run_command(command, "Running all tests")


def run_coverage_tests():
    """Run tests with coverage report"""
    # First install coverage if not available
    try:
        import coverage
    except ImportError:
        print("Installing coverage...")
        subprocess.run([sys.executable, "-m", "pip", "install", "coverage"], check=True)

    commands = [
        "python -m coverage run -m pytest tests/",
        "python -m coverage report -m",
        "python -m coverage html"
    ]

    for i, command in enumerate(commands):
        descriptions = [
            "Running tests with coverage",
            "Generating coverage report",
            "Generating HTML coverage report"
        ]
        if not run_command(command, descriptions[i]):
            return False

    print("\n📊 Coverage report generated in htmlcov/index.html")
    return True


def run_quick_test():
    """Run a quick smoke test"""
    print("🚀 Running quick smoke test...")

    # Add src to Python path
    src_path = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_path))

    try:
        # Test basic imports
        from api.data_manager import DataManager
        from api.fmp_client import FMPClient
        from api.tiingo_client import TiingoClient
        print("✅ All imports successful")

        # Test DataManager initialization
        dm = DataManager()
        print("✅ DataManager initialization successful")

        print("✅ Quick smoke test passed!")
        return True

    except Exception as e:
        print(f"❌ Quick smoke test failed: {e}")
        return False


def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description="Stock Analyzer Test Runner")
    parser.add_argument(
        '--type',
        choices=['quick', 'unit', 'integration', 'api', 'all', 'coverage'],
        default='unit',
        help='Type of tests to run (default: unit)'
    )
    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Check dependencies before running tests'
    )
    parser.add_argument(
        '--check-keys',
        action='store_true',
        help='Check API key configuration'
    )

    args = parser.parse_args()

    print("🧪 Stock Analyzer Test Runner")
    print("=" * 60)

    # Check dependencies if requested
    if args.check_deps:
        if not check_dependencies():
            sys.exit(1)

    # Check API keys if requested
    if args.check_keys:
        check_api_keys()

    # Run tests based on type
    success = True

    if args.type == 'quick':
        success = run_quick_test()
    elif args.type == 'unit':
        success = run_unit_tests()
    elif args.type == 'integration':
        success = run_integration_tests()
    elif args.type == 'api':
        success = run_api_tests()
    elif args.type == 'all':
        success = run_all_tests()
    elif args.type == 'coverage':
        success = run_coverage_tests()

    # Summary
    print(f"\n{'='*60}")
    if success:
        print("🎉 All tests completed successfully!")
    else:
        print("💥 Some tests failed!")
    print(f"{'='*60}")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()