#!/usr/bin/env bash
# Smoke test for the model gateway
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8000}"
CLIENT_KEY="${CLIENT_KEY:-sk-gw-client-test}"

echo "Running smoke tests against $GATEWAY_URL..."

# 1. Health check
echo -n "  Health live... "
if curl -sf "$GATEWAY_URL/health/live" | grep -q '"ok"'; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# 2. List models
echo -n "  List models... "
if curl -sf "$GATEWAY_URL/v1/models" -H "Authorization: Bearer $CLIENT_KEY" | grep -q '"object"'; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# 3. Chat completion (non-streaming)
echo -n "  Chat completion... "
RESPONSE=$(curl -sf "$GATEWAY_URL/v1/chat/completions" \
    -H "Authorization: Bearer $CLIENT_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"auto","messages":[{"role":"user","content":"Reply only: OK"}],"max_tokens":10,"stream":false}')

if echo "$RESPONSE" | grep -q '"choices"'; then
    echo "PASS"
else
    echo "FAIL"
    echo "Response: $RESPONSE"
    exit 1
fi

echo ""
echo "All smoke tests passed!"
