---
title: "Usage"
schema_type: common
status: published
owner: core-maintainer
purpose: "Usage guide for LLC Manager."
tags:
  - guide
  - usage
---

This guide covers common usage patterns for LLC Manager.

## Installation

### From PyPI

```bash
pip install llc-manager
```

### From Source

```bash
git clone https://github.com/ByronWilliamsCPA/llc-manager
cd llc_manager
uv sync --all-extras
```

## Library Usage

### Basic Import

```python
from llc_manager import __version__

print(f"Version: {__version__}")
```

### Logging

```python
from llc_manager.utils.logging import get_logger, setup_logging

# Setup logging
setup_logging(level="DEBUG", json_logs=False)

# Get a logger
logger = get_logger(__name__)
logger.info("Hello from LLC Manager")
```
