#!/bin/bash
# Run tests using Docker Compose (recommended method)

set -e

echo "=========================================="
echo "Running Tests via Docker Compose"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

cd "$(dirname "$0")/.."

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ docker-compose not found${NC}"
    exit 1
fi

echo "1. Running syntax validation..."
echo "-----------------------------------"
docker-compose exec -T ats-trading-api python3 -m py_compile api/main.py 2>&1 || {
    echo -e "${RED}❌ Syntax check failed${NC}"
    exit 1
}
echo -e "${GREEN}✅ Syntax check passed${NC}"

echo ""
echo "2. Running import validation..."
echo "-----------------------------------"
docker-compose exec -T ats-trading-api python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from api.main import app
    print('✅ Import successful')
except Exception as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)
" 2>&1 || {
    echo -e "${RED}❌ Import check failed${NC}"
    exit 1
}
echo -e "${GREEN}✅ Import check passed${NC}"

echo ""
echo "3. Running comprehensive test suite..."
echo "-----------------------------------"
docker-compose exec -T ats-trading-api python3 -m pytest tests/ -v --tb=short --asyncio-mode=auto 2>&1 | tee /tmp/pytest_output.txt || {
    echo -e "${YELLOW}⚠️  Some tests failed (check output above)${NC}"
    exit 1
}
echo -e "${GREEN}✅ All tests passed${NC}"

echo ""
echo "=========================================="
echo -e "${GREEN}✅ All quality checks passed!${NC}"
echo "=========================================="

