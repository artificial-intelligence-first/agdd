---
title: AGDD MCP Server - Exposing Agents as Tools
last_synced: 2025-10-25
description: Expose AGDD agents and skills as MCP tools for Claude Desktop and other MCP clients
---

# AGDD MCP Server

This guide covers how to expose AGDD agents and skills as MCP (Model Context Protocol) tools, allowing external clients like Claude Desktop to invoke them.

## Overview

The AGDD MCP Server allows you to:

- **Expose Agents**: Make AGDD agents (MAG/SAG) available as MCP tools
- **Expose Skills**: Optionally expose AGDD skills as MCP tools
- **Claude Desktop Integration**: Use agents directly from Claude Desktop
- **MCP Client Support**: Compatible with any MCP-compliant client

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│               Claude Desktop (MCP Client)                 │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  MCP Tools Available:                               │ │
│  │  • offer-orchestrator-mag                           │ │
│  │  • compensation-advisor-sag                         │ │
│  │  • salary-band-lookup                               │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────┘
                       │ JSON-RPC 2.0 (stdio)
                       ▼
          ┌────────────────────────┐
          │   agdd mcp serve       │
          │  (MCP Server Process)  │
          └────────────┬───────────┘
                       │
          ┌────────────┼────────────────────┐
          │            │                    │
          ▼            ▼                    ▼
   ┌──────────┐  ┌──────────┐      ┌──────────┐
   │offer-orch│  │comp-advis│  ... │  Skills  │
   │-mag      │  │-sag      │      │ (optional)│
   └──────────┘  └──────────┘      └──────────┘
```

## Installation

Install the MCP server dependencies:

```bash
# Install with MCP server support
pip install -e ".[mcp-server]"

# Or using uv
uv pip install -e ".[mcp-server]"
```

This installs the `mcp` package (FastMCP SDK) required for the server.

## Quick Start

### 1. Start MCP Server

```bash
# Start server exposing all agents
agdd mcp serve

# Start with specific agents only
agdd mcp serve --filter-agents offer-orchestrator-mag,compensation-advisor-sag

# Start with skills enabled
agdd mcp serve --agents --skills
```

### 2. Configure Claude Desktop

Add AGDD to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "agdd": {
      "command": "agdd",
      "args": ["mcp", "serve"]
    }
  }
}
```

For filtered agents:

```json
{
  "mcpServers": {
    "agdd": {
      "command": "agdd",
      "args": [
        "mcp",
        "serve",
        "--filter-agents",
        "offer-orchestrator-mag"
      ]
    }
  }
}
```

### 3. Restart Claude Desktop

Restart Claude Desktop to load the MCP server configuration.

### 4. Use Agents from Claude

In Claude Desktop, you can now invoke AGDD agents:

```
User: Can you generate a compensation offer for a Senior Engineer with 8 years of experience?

Claude: I'll use the offer-orchestrator-mag tool to generate that for you.

[Uses offer-orchestrator-mag tool with appropriate payload]

Based on the analysis, here's the recommended compensation package:
- Base Salary: $150,000 - $180,000
- Equity: 0.15% - 0.25%
- Sign-on Bonus: $25,000
...
```

## CLI Commands

### `agdd mcp serve`

Start AGDD as an MCP server.

**Options:**

- `--agents/--no-agents` - Expose agents as MCP tools (default: True)
- `--skills/--no-skills` - Expose skills as MCP tools (default: False)
- `--filter-agents <slugs>` - Comma-separated list of agent slugs to expose
- `--filter-skills <ids>` - Comma-separated list of skill IDs to expose

**Examples:**

```bash
# All agents
agdd mcp serve

# Specific agents
agdd mcp serve --filter-agents offer-orchestrator-mag,compensation-advisor-sag

# Agents and skills
agdd mcp serve --agents --skills

# Only skills
agdd mcp serve --no-agents --skills

# Specific skills
agdd mcp serve --no-agents --skills --filter-skills skill.salary-band-lookup
```

## Programmatic Usage

You can also create an MCP server programmatically:

```python
from pathlib import Path
from agdd.mcp.server_provider import create_server

# Create server
server = create_server(
    base_path=Path.cwd(),
    expose_agents=True,
    expose_skills=False,
    agent_filter=["offer-orchestrator-mag"],
    skill_filter=None,
)

# Run server (blocks)
server.run(transport="stdio")
```

### Custom Server Configuration

```python
from agdd.mcp.server_provider import AGDDMCPServer
from pathlib import Path

# Create custom server
server = AGDDMCPServer(
    base_path=Path("/path/to/agdd"),
    expose_agents=True,
    expose_skills=True,
    agent_filter=["offer-orchestrator-mag", "compensation-advisor-sag"],
    skill_filter=["skill.salary-band-lookup"],
)

# Access FastMCP instance for advanced configuration
mcp = server.mcp

# Run server
server.run(transport="stdio")
```

## Tool Schema

Each AGDD agent is exposed as an MCP tool with the following schema:

**Tool Name**: Agent slug (e.g., `offer-orchestrator-mag`)

**Description**: Agent name and role (e.g., "Offer Orchestrator (main agent)")

**Input Schema**: Derived from the agent's input contract schema

**Output**: Matches the agent's output contract schema

**Example Tool Definition:**

```json
{
  "name": "offer-orchestrator-mag",
  "description": "Offer Orchestrator (main agent)\n\nInput Schema: catalog/contracts/offer_orchestrator_input.json",
  "inputSchema": {
    "type": "object",
    "properties": {
      "role": {
        "type": "string",
        "description": "Job role/title"
      },
      "level": {
        "type": "string",
        "description": "Seniority level"
      },
      "experience_years": {
        "type": "number",
        "description": "Years of experience"
      }
    },
    "required": ["role", "level", "experience_years"]
  }
}
```

## Agent Execution

When an MCP tool is invoked:

1. **Input Validation**: Payload is validated against the agent's input schema
2. **Agent Execution**: `invoke_mag()` is called with the payload
3. **Output Return**: Agent output is returned to the MCP client
4. **Error Handling**: Exceptions are caught and returned as MCP errors

**Execution Flow:**

```python
# MCP client sends tools/call request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "offer-orchestrator-mag",
    "arguments": {
      "role": "Senior Engineer",
      "level": "Senior",
      "experience_years": 8
    }
  }
}

# AGDD executes agent
output = invoke_mag(
    slug="offer-orchestrator-mag",
    payload={"role": "Senior Engineer", ...},
    base_dir=Path(".runs/mcp"),
    context={}
)

# MCP server returns result
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"salary_range\": ...\n}"
      }
    ]
  }
}
```

## Run Artifacts

Agent executions triggered via MCP are stored in `.runs/mcp/`:

```
.runs/mcp/
└── agents/
    └── offer-orchestrator-mag/
        └── <RUN_ID>/
            ├── logs.jsonl
            ├── metrics.json
            ├── summary.json
            └── output.json
```

You can analyze these runs using AGDD's observability tools:

```bash
# Query runs
agdd data query --agent offer-orchestrator-mag --limit 10

# Search logs
agdd data search "compensation" --agent offer-orchestrator-mag
```

## Advanced Configuration

### Using Absolute Paths

For system-wide installation, use absolute paths:

```json
{
  "mcpServers": {
    "agdd": {
      "command": "/usr/local/bin/agdd",
      "args": ["mcp", "serve"],
      "env": {
        "AGDD_BASE_PATH": "/path/to/agdd/catalog"
      }
    }
  }
}
```

### Virtual Environment

If AGDD is in a virtual environment:

```json
{
  "mcpServers": {
    "agdd": {
      "command": "/path/to/venv/bin/agdd",
      "args": ["mcp", "serve"]
    }
  }
}
```

### Environment Variables

Pass environment variables for LLM providers:

```json
{
  "mcpServers": {
    "agdd": {
      "command": "agdd",
      "args": ["mcp", "serve"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        "AGDD_PROVIDER": "openai"
      }
    }
  }
}
```

## Filtering Agents

### By Role

Expose only main agents or sub-agents:

```bash
# Main agents only (from catalog/agents/main/)
agdd mcp serve --filter-agents offer-orchestrator-mag

# Sub-agents only (from catalog/agents/sub/)
agdd mcp serve --filter-agents compensation-advisor-sag,salary-calculator-sag
```

### By Risk Class

Filter agents by risk classification in a wrapper script:

```bash
#!/bin/bash
# expose-low-risk-agents.sh

# Get low-risk agents from registry
LOW_RISK_AGENTS=$(
  yq '.tasks[] | select(.risk == "low") | .default' \
    catalog/registry/agents.yaml | \
  cut -d'.' -f2 | \
  cut -d'@' -f1 | \
  paste -sd,
)

# Start MCP server
agdd mcp serve --filter-agents "$LOW_RISK_AGENTS"
```

Then use in Claude Desktop:

```json
{
  "mcpServers": {
    "agdd-safe": {
      "command": "/path/to/expose-low-risk-agents.sh"
    }
  }
}
```

## Troubleshooting

### Server Not Starting

**Check logs**: Claude Desktop logs MCP server output to:

- **macOS**: `~/Library/Logs/Claude/mcp-server-agdd.log`
- **Windows**: `%APPDATA%\Claude\Logs\mcp-server-agdd.log`

**Verify installation**:

```bash
# Check agdd is available
which agdd

# Test MCP server
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | agdd mcp serve
```

### Tools Not Appearing

**Restart Claude Desktop** after configuration changes.

**Check agent discovery**:

```bash
# List available agents
ls catalog/agents/main/
ls catalog/agents/sub/
```

**Validate agent YAML**:

```bash
# Check agent.yaml exists
ls catalog/agents/main/offer-orchestrator-mag/agent.yaml
```

### Execution Failures

**Check run logs**:

```bash
# View recent runs
agdd data query --agent offer-orchestrator-mag --limit 5

# Search for errors
agdd data search "error" --agent offer-orchestrator-mag
```

**Verify agent dependencies**:

```bash
# Test agent locally
echo '{"role":"Engineer","level":"Mid","experience_years":5}' | \
  agdd agent run offer-orchestrator-mag
```

### MCP SDK Not Installed

**Error**: `ImportError: No module named 'mcp'`

**Solution**:

```bash
pip install -e ".[mcp-server]"
```

## Security Considerations

### 1. Expose Only Trusted Agents

Only expose agents you trust to be invoked by Claude Desktop:

```bash
# Explicitly allow specific agents
agdd mcp serve --filter-agents offer-orchestrator-mag
```

### 2. Agent Permissions

Be aware that agents exposed via MCP inherit their declared permissions:

```yaml
# catalog/agents/main/offer-orchestrator-mag/agent.yaml
depends_on:
  skills:
    - skill.salary-band-lookup  # Has mcp:pg-readonly permission
```

### 3. Input Validation

All agent inputs are validated against JSON schemas, but ensure schemas properly constrain inputs:

```json
{
  "properties": {
    "role": {
      "type": "string",
      "maxLength": 100
    },
    "experience_years": {
      "type": "number",
      "minimum": 0,
      "maximum": 50
    }
  }
}
```

### 4. Rate Limiting

Consider implementing rate limiting for production use:

```python
from agdd.mcp.server_provider import AGDDMCPServer

class RateLimitedMCPServer(AGDDMCPServer):
    def __init__(self, *args, max_calls_per_minute=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_calls = max_calls_per_minute
        # Implement rate limiting logic
```

## Examples

### Example 1: Compensation Agent in Claude Desktop

**Configuration**:

```json
{
  "mcpServers": {
    "agdd-compensation": {
      "command": "agdd",
      "args": [
        "mcp",
        "serve",
        "--filter-agents",
        "offer-orchestrator-mag,compensation-advisor-sag"
      ]
    }
  }
}
```

**Usage in Claude**:

```
User: Generate a compensation offer for a Staff Engineer with 12 years of experience at a Series B startup.

Claude: I'll use the offer-orchestrator-mag tool to create a comprehensive compensation package.

[Invokes offer-orchestrator-mag with appropriate parameters]

Here's the recommended compensation offer:

**Base Compensation:**
- Base Salary: $185,000 - $220,000
- Target Annual Bonus: 15% ($27,750 - $33,000)

**Equity:**
- Stock Options: 0.25% - 0.35% of fully diluted shares
- 4-year vesting with 1-year cliff

**Additional Benefits:**
- Sign-on Bonus: $35,000
- Annual Learning Budget: $3,000
- Remote Work Stipend: $500/month

This offer is competitive for a Staff Engineer with 12 years of experience in a Series B environment.
```

### Example 2: Multi-Agent Workflow

Expose multiple specialized agents:

```bash
agdd mcp serve --filter-agents \
  offer-orchestrator-mag,\
  compensation-advisor-sag,\
  equity-calculator-sag,\
  benefits-optimizer-sag
```

Claude can then orchestrate complex workflows using multiple agents.

## Performance Considerations

### Cold Start

First invocation may be slower due to:
- Agent loading and initialization
- Dependency resolution
- Schema validation setup

**Mitigation**: Keep MCP server running (it remains active while Claude Desktop is open).

### Concurrent Requests

Currently, each agent invocation runs sequentially. For high-volume use cases, consider:

1. **Multiple MCP Servers**: Run separate instances for different agent groups
2. **Agent Pooling**: Implement agent instance pooling (future feature)
3. **Async Execution**: Use async agent execution (future feature)

## Related Documentation

- [MCP Integration Guide](./mcp-integration.md) - Using external MCP servers from AGDD
- [Agent Development Guide](./agent-development.md) - Creating agents
- [API Usage Guide](./api-usage.md) - HTTP API for agent execution
- [Cost Optimization](./cost-optimization.md) - Managing agent execution costs

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Desktop MCP Configuration](https://docs.anthropic.com/claude/docs/model-context-protocol)
