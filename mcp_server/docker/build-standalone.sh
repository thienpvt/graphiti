#!/bin/bash
# Script to build and push standalone Docker image with both Neo4j and FalkorDB drivers
# Run from mcp_server/docker; graphiti-core is installed from repository source.

set -e

REPO_ROOT=$(cd ../.. && pwd)

# Get project versions from local source.
MCP_VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('${REPO_ROOT}/mcp_server/pyproject.toml', 'rb'))['project']['version'])")
GRAPHITI_CORE_VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('${REPO_ROOT}/pyproject.toml', 'rb'))['project']['version'])")

# Get build metadata
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Build standalone image from repository-root context.
echo "Building standalone Docker image..."
docker build \
  --build-arg MCP_SERVER_VERSION="${MCP_VERSION}" \
  --build-arg BUILD_DATE="${BUILD_DATE}" \
  --build-arg VCS_REF="${VCS_REF}" \
  -f "${REPO_ROOT}/mcp_server/docker/Dockerfile.standalone" \
  -t "zepai/knowledge-graph-mcp:standalone" \
  -t "zepai/knowledge-graph-mcp:${MCP_VERSION}-standalone" \
  -t "zepai/knowledge-graph-mcp:${MCP_VERSION}-graphiti-${GRAPHITI_CORE_VERSION}-standalone" \
  "${REPO_ROOT}"

echo ""
echo "Build complete!"
echo "  MCP Server Version: ${MCP_VERSION}"
echo "  Graphiti Core Version: ${GRAPHITI_CORE_VERSION}"
echo "  Build Date: ${BUILD_DATE}"
echo "  VCS Ref: ${VCS_REF}"
echo ""
echo "Image tags:"
echo "  - zepai/knowledge-graph-mcp:standalone"
echo "  - zepai/knowledge-graph-mcp:${MCP_VERSION}-standalone"
echo "  - zepai/knowledge-graph-mcp:${MCP_VERSION}-graphiti-${GRAPHITI_CORE_VERSION}-standalone"
echo ""
echo "To push to DockerHub:"
echo "  docker push zepai/knowledge-graph-mcp:standalone"
echo "  docker push zepai/knowledge-graph-mcp:${MCP_VERSION}-standalone"
echo "  docker push zepai/knowledge-graph-mcp:${MCP_VERSION}-graphiti-${GRAPHITI_CORE_VERSION}-standalone"
echo ""
echo "Or push all tags:"
echo "  docker push --all-tags zepai/knowledge-graph-mcp"
