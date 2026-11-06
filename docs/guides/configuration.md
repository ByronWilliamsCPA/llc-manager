---
title: "Configuration"
schema_type: common
status: published
owner: core-maintainer
purpose: "Configuration guide for LLC Manager."
tags:
  - guide
  - configuration
---

This guide covers all configuration options for LLC Manager.

## Environment Variables

LLC Manager uses environment variables for configuration:

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `JSON_LOGS` | Enable JSON log format | `false` |
| `LLC_MANAGER_API_KEY` | Shared `X-API-Key` for `/api/v1` (`LLC_MANAGER_SERVICE_API_KEY` is read when unset). Unset or empty means `/api/v1` answers 503. At least 32 characters outside development. | unset |
| `LLC_MANAGER_DOCUMENTS_ROOT` | Directory that holds stored document files | `/data/docs` |

## Configuration File

Create a `.env` file in your project root:

```bash
# Logging
LOG_LEVEL=INFO
JSON_LOGS=false

# Add your configuration here
```

## Pydantic Settings

Configuration is managed via Pydantic Settings for type safety:

```python
from llc_manager.core.config import settings

# Access settings
print(settings.log_level)
```

## Development vs Production

### Development

```bash
LOG_LEVEL=DEBUG
JSON_LOGS=false
```

### Production

```bash
LOG_LEVEL=INFO
JSON_LOGS=true
```
