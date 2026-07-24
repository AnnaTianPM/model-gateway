# Model Gateway

> LAN AI API Gateway with smart routing, multi-provider failover, and OpenAI-compatible interface.
>
> Forked from [zk-2025/model-gateway](https://github.com/zk-2025/model-gateway) v1.6.0 (CC BY-NC 4.0).

## Features

- **OpenAI-compatible API**: `/v1/chat/completions`, `/v1/models` (streaming + non-streaming)
- **Smart Routing**: Static task classification → model capability scoring → dynamic health-aware provider selection
- **Multi-Provider Failover**: Same-model provider switch first, then cross-model fallback (max 4 attempts)
- **Dynamic Health Monitoring**: Beta/Wilson reliability, multi-window aggregation (5m/1h/24h), circuit breaker
- **Logical Models**: `auto`, `auto-fast`, `auto-best`, `auto-coding`, `auto-reasoning`, `auto-writing`, `auto-translation`, `auto-vision`, `auto-tools`
- **Client API Keys**: Per-device keys with hash storage, RPM limiting, model permissions
- **Provider Key Encryption**: Fernet encryption with master key
- **Streaming Safety**: First-token failover allowed; post-token safe termination (no cross-model continuation)
- **Web Dashboard**: Overview, Providers, Models, Health, Routing preview, Client Keys
- **Docker Deployment**: One-command startup, health checks, versioned deploy/rollback
- **SQLite Storage**: 10 tables with migration system, no external database needed

## Quick Start

### Docker (Recommended)

```bash
# 1. Clone
git clone https://github.com/AnnaTianPM/model-gateway.git
cd model-gateway

# 2. Configure
cp .env.example .env
# Edit .env: set ADMIN_TOKEN and GATEWAY_MASTER_KEY

# 3. Start
./scripts/start.sh

# 4. Check
curl http://localhost:8000/health/live
```

### Direct Python

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Set environment variables
export DATABASE_PATH=data/gateway.db
export ADMIN_TOKEN=your-admin-token
export GATEWAY_MASTER_KEY=your-encryption-key

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## LAN Configuration

### Gateway Setup

1. **Fix IP**: Set DHCP reservation on your router (e.g., `192.168.1.50`)
2. **Firewall**: Open port 8000 for LAN subnet only
3. **No public exposure**: Do NOT set up port forwarding on your router

### Client Configuration

```
Base URL: http://192.168.1.50:8000/v1
API Key:  sk-gw-client-xxxxxxxx  (from Dashboard → Client Keys)
Model:    auto
```

Each device should use its own Client Key.

## Adding Providers

1. Open Dashboard at `http://<gateway-ip>:8000/`
2. Login with Admin Token
3. Go to **Providers** → Add Provider
4. Enter: Name, Base URL, API Key
5. Click **Fetch Models** to auto-discover available models
6. Routes are created automatically

### Supported Providers

Any OpenAI-compatible provider:
- NVIDIA (integrate.api.nvidia.com)
- Gemini
- ModelScope (api-inference.modelscope.cn)
- SiliconFlow
- OpenRouter
- Groq
- And more

## Architecture

```
Client Request → Auth → Feature Extraction → Rule Classifier →
Hard Filter (capabilities/health) → Model Selection (static scores) →
Provider Selection (reliability/TTFT) → Proxy → Failover if needed
```

### Key Modules

| Module | Responsibility |
|--------|----------------|
| `app/routing/` | Request classification, model/provider selection, fallback |
| `app/health/` | Probes, metrics aggregation, circuit breaker, scheduler |
| `app/proxy/` | Non-streaming/streaming proxy with safety guarantees |
| `app/storage/` | SQLite, schema, migrations, repositories |
| `app/auth/` | Client keys, admin auth, provider key encryption |
| `app/models/` | Canonical models, static scores, capabilities |
| `app/providers/` | Provider adapters, error classification |
| `app/api/` | OpenAI + Admin API routes |
| `app/dashboard/` | Web management panel |

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_HOST` | `0.0.0.0` | Listen address |
| `GATEWAY_PORT` | `8000` | Listen port |
| `ADMIN_TOKEN` | (must set) | Admin authentication token |
| `GATEWAY_MASTER_KEY` | (must set) | Fernet key for provider key encryption |
| `DATABASE_PATH` | `/app/data/gateway.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_PROMPT_CONTENT` | `false` | Log full prompts (security risk) |
| `FORCE_RESPONSE_LANGUAGE` | `off` | Force response language |

### Config Files

- `config/model_scores.yaml` — Static model capability scores
- `config/routing_rules.yaml` — Health thresholds, routing strategies, task weights
- `config/provider_presets.yaml` — Preset provider configurations

## Deployment

### Versioned Deploy

```bash
./scripts/deploy.sh v0.1.0
```

### Backup

```bash
./scripts/backup.sh
```

### Rollback

```bash
./scripts/rollback.sh v0.1.0
```

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# All tests
pytest -q
```

## Security

- Provider API keys are encrypted (Fernet) before database storage
- Client keys stored as SHA-256 hashes (never plaintext)
- Admin and client authentication are fully separated
- No keys in logs, API responses, or frontend HTML
- No public internet exposure by default

## License

CC BY-NC 4.0 — Personal, non-commercial use only.
See [LEGAL_NOTES.md](LEGAL_NOTES.md) for details.

## Acknowledgments

Based on [zk-2025/model-gateway](https://github.com/zk-2025/model-gateway) by [zk-2025](https://github.com/zk-2025).
