#!/bin/bash
# Run quality checks: mypy, tests, and linting

set -e

echo "=========================================="
echo "Running Quality Checks"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if mypy is installed
if ! command -v mypy &> /dev/null; then
    echo -e "${YELLOW}⚠️  mypy not found. Installing mypy[pydantic,fastapi]...${NC}"
    pip install mypy[pydantic,fastapi] --quiet
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}⚠️  pytest not found. Installing pytest...${NC}"
    pip install pytest pytest-asyncio --quiet
fi

echo "1. Running mypy type checking..."
echo "-----------------------------------"
cd agentic_system_trading
if mypy api/main.py api/routers/ api/services/ --ignore-missing-imports --show-error-codes 2>&1 | tee /tmp/mypy_output.txt; then
    echo -e "${GREEN}✅ mypy passed${NC}"
    mypy_passed=true
else
    echo -e "${RED}❌ mypy found type errors${NC}"
    mypy_passed=false
fi
cd ..

echo ""
echo "2. Running syntax check..."
echo "-----------------------------------"
if python3 -m py_compile agentic_system_trading/api/main.py 2>&1; then
    echo -e "${GREEN}✅ Syntax check passed${NC}"
    syntax_passed=true
else
    echo -e "${RED}❌ Syntax errors found${NC}"
    syntax_passed=false
fi

echo ""
echo "3. Running comprehensive tests..."
echo "-----------------------------------"
cd agentic_system_trading
if python3 -m pytest tests/test_new_routers.py tests/test_router_endpoints_integration.py -v --tb=short --asyncio-mode=auto 2>&1 | tee /tmp/pytest_output.txt; then
    echo -e "${GREEN}✅ Tests passed${NC}"
    tests_passed=true
else
    echo -e "${YELLOW}⚠️  Some tests failed (check output above)${NC}"
    tests_passed=false
fi
cd ..

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
if [ "$mypy_passed" = true ] && [ "$syntax_passed" = true ] && [ "$tests_passed" = true ]; then
    echo -e "${GREEN}✅ All quality checks passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some quality checks failed${NC}"
    echo "  - mypy: $([ "$mypy_passed" = true ] && echo "✅" || echo "❌")"
    echo "  - syntax: $([ "$syntax_passed" = true ] && echo "✅" || echo "❌")"
    echo "  - tests: $([ "$tests_passed" = true ] && echo "✅" || echo "❌")"
    exit 1
fi

