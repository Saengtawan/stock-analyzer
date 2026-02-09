#!/bin/bash
#
# Config Integration Test Runner
#
# Runs comprehensive config validation and integration tests
#
# Usage:
#   ./tests/run_config_tests.sh
#   ./tests/run_config_tests.sh --verbose
#   ./tests/run_config_tests.sh --coverage
#

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================================================"
echo "Config Integration Test Suite"
echo "========================================================================"
echo ""

# Parse arguments
VERBOSE=""
COVERAGE=""
for arg in "$@"; do
    case $arg in
        --verbose|-v)
            VERBOSE="-v"
            shift
            ;;
        --coverage)
            COVERAGE="1"
            shift
            ;;
    esac
done

# Change to project root
cd "$PROJECT_ROOT"

# Set PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"

echo "Test 1: Config Validation Rules"
echo "------------------------------------------------------------------------"
if [ -n "$VERBOSE" ]; then
    python -m pytest tests/test_config_integration.py::TestConfigValidation -v
else
    python -m pytest tests/test_config_integration.py::TestConfigValidation -q
fi
echo -e "${GREEN}✅ Test 1 Passed${NC}"
echo ""

echo "Test 2: Config Scenarios"
echo "------------------------------------------------------------------------"
if [ -n "$VERBOSE" ]; then
    python -m pytest tests/test_config_integration.py::TestConfigScenarios -v
else
    python -m pytest tests/test_config_integration.py::TestConfigScenarios -q
fi
echo -e "${GREEN}✅ Test 2 Passed${NC}"
echo ""

echo "Test 3: Edge Cases"
echo "------------------------------------------------------------------------"
if [ -n "$VERBOSE" ]; then
    python -m pytest tests/test_config_integration.py::TestConfigEdgeCases -v
else
    python -m pytest tests/test_config_integration.py::TestConfigEdgeCases -q
fi
echo -e "${GREEN}✅ Test 3 Passed${NC}"
echo ""

echo "Test 4: YAML Integration"
echo "------------------------------------------------------------------------"
if [ -n "$VERBOSE" ]; then
    python -m pytest tests/test_config_integration.py::TestConfigYAMLIntegration -v
else
    python -m pytest tests/test_config_integration.py::TestConfigYAMLIntegration -q
fi
echo -e "${GREEN}✅ Test 4 Passed${NC}"
echo ""

echo "Test 5: Backward Compatibility"
echo "------------------------------------------------------------------------"
if [ -n "$VERBOSE" ]; then
    python -m pytest tests/test_config_integration.py::TestBackwardCompatibility -v
else
    python -m pytest tests/test_config_integration.py::TestBackwardCompatibility -q
fi
echo -e "${GREEN}✅ Test 5 Passed${NC}"
echo ""

echo "Test 6: Config Tools CLI"
echo "------------------------------------------------------------------------"
if [ -n "$VERBOSE" ]; then
    python -m pytest tests/test_config_integration.py::TestConfigTools -v
else
    python -m pytest tests/test_config_integration.py::TestConfigTools -q
fi
echo -e "${GREEN}✅ Test 6 Passed${NC}"
echo ""

# Coverage report
if [ -n "$COVERAGE" ]; then
    echo "========================================================================"
    echo "Coverage Report"
    echo "========================================================================"
    python -m pytest tests/test_config_integration.py --cov=src/config --cov-report=term-missing
    echo ""
fi

echo "========================================================================"
echo -e "${GREEN}✅ ALL TESTS PASSED!${NC}"
echo "========================================================================"
echo ""
echo "Summary:"
echo "  - Config Validation: ✅"
echo "  - Config Scenarios: ✅"
echo "  - Edge Cases: ✅"
echo "  - YAML Integration: ✅"
echo "  - Backward Compatibility: ✅"
echo "  - Config Tools CLI: ✅"
echo ""
echo "Total: 6/6 test suites passed"
echo ""

exit 0
