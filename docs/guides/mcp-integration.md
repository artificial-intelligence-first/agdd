# Model Context Protocol (MCP) Integration

This guide covers the integration of Model Context Protocol (MCP) servers with AGDD agents, enabling access to external tools, data sources, and services through a standardized interface.

## Overview

The Model Context Protocol (MCP) is an open protocol that standardizes how AI applications interact with external tools and data sources. AGDD integrates MCP to provide agents with:

- **File system access**: Read/write files with security controls
- **Git operations**: Repository management and code analysis
- **Knowledge graphs**: Persistent memory and entity relationships
- **Web fetching**: Content retrieval and conversion
- **Database access**: Query structured data sources
- **Custom tools**: Extend agent capabilities with domain-specific tools

## MCP Architecture in AGDD

```
┌─────────────────────────────────────────────────────────────┐
│                    AGDD Agent Runtime                        │
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │     MAG      │────────▶│     SAG      │                  │
│  │ Orchestrator │         │  Specialists │                  │
│  └──────┬───────┘         └──────┬───────┘                  │
└─────────┼────────────────────────┼──────────────────────────┘
          │                        │
          └────────────┬───────────┘
                       ▼
          ┌────────────────────────┐
          │   MCP Client Layer     │
          │  (LLM-managed calls)   │
          └────────────┬───────────┘
                       │
          ┌────────────┼───────────────────────────┐
          │            │                           │
          ▼            ▼                           ▼
   ┌──────────┐  ┌──────────┐            ┌──────────────┐
   │Filesystem│  │   Git    │    ...     │   Custom     │
   │  Server  │  │  Server  │            │   Servers    │
   └──────────┘  └──────────┘            └──────────────┘
```

### Key Concepts

- **MCP Server**: External service providing tools (filesystem, git, database, etc.)
- **MCP Client**: LLM runtime that invokes MCP servers based on agent instructions
- **Tool Discovery**: Automatic exposure of available tools to agents
- **Rate Limiting**: Per-server request throttling
- **Observability**: MCP call tracking in `.runs/` artifacts

## Available MCP Servers

AGDD includes pre-configured MCP servers in `.mcp/servers/`:

### 1. Filesystem Server (`filesystem.yaml`)

Provides secure file operations with configurable access controls.

```yaml
# .mcp/servers/filesystem.yaml
server_id: filesystem
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-filesystem@2025.8.21"
  - "."  # Repository root
description: Secure file operations with configurable access controls
scopes:
  - read:files
  - write:files
limits:
  rate_per_min: 60
  timeout_s: 30
```

**Configuration Details:**
- **server_id**: Unique identifier for the server
- **command**: Execution command (npx for Node.js packages)
- **args**: Package name with pinned version and repository path
- **limits.rate_per_min**: Maximum requests per minute
- **limits.timeout_s**: Request timeout in seconds

**Available Tools:**
- `read_file(path)`: Read file contents
- `write_file(path, content)`: Write/update file
- `list_directory(path)`: List directory contents
- `create_directory(path)`: Create new directory
- `move_file(source, dest)`: Move/rename files
- `search_files(pattern)`: Search by filename pattern

**Security:**
- Restricted to repository root (`.`)
- No access to parent directories
- Rate limited to prevent abuse

### 2. Git Server (`git.yaml`)

Tools for Git repository operations.

```yaml
# .mcp/servers/git.yaml
server_id: git
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-git@1.0.0"
  - --repository
  - "."  # Repository root
description: Tools to read, search, and manipulate Git repositories
scopes:
  - read:git
  - write:git
limits:
  rate_per_min: 30
  timeout_s: 60
```

**Available Tools:**
- `git_status()`: Get repository status
- `git_diff(ref)`: Show changes
- `git_log(limit)`: View commit history
- `git_show(commit)`: Show commit details
- `git_blame(file)`: Show line-by-line authorship
- `git_search(query)`: Search commit messages

**Use Cases:**
- Code review agents analyzing PRs
- Documentation generators tracking changes
- Compliance agents auditing commits

### 3. Memory Server (`memory.yaml`)

Knowledge graph-based persistent memory.

```yaml
# .mcp/servers/memory.yaml
server_id: memory
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-memory@2025.9.25"
description: Knowledge graph-based persistent memory system
scopes:
  - read:memory
  - write:memory
limits:
  rate_per_min: 120
  timeout_s: 20
```

**Available Tools:**
- `create_entity(name, type, properties)`: Create knowledge node
- `create_relation(from, to, type)`: Link entities
- `query_entities(filters)`: Search knowledge graph
- `get_entity(id)`: Retrieve entity details
- `update_entity(id, properties)`: Update entity
- `delete_entity(id)`: Remove entity

**Use Cases:**
- Agents maintaining context across runs
- Building domain knowledge bases
- Tracking relationships and dependencies

### 4. Fetch Server (`fetch.yaml`)

Web content fetching and conversion.

```yaml
# .mcp/servers/fetch.yaml
server_id: fetch
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-fetch@1.0.0"
description: Web content fetching and conversion for efficient LLM usage
scopes:
  - read:web
limits:
  rate_per_min: 30
  timeout_s: 30
```

**Available Tools:**
- `fetch_url(url)`: Retrieve web content
- `fetch_html(url)`: Get HTML content
- `fetch_markdown(url)`: Convert HTML to Markdown
- `fetch_text(url)`: Extract plain text

**Use Cases:**
- Research agents gathering information
- Documentation generators pulling external references
- Monitoring agents checking website status

### 5. PostgreSQL Server (`pg-readonly.yaml`)

Read-only database access.

```yaml
# .mcp/servers/pg-readonly.yaml
server_id: pg-readonly
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-postgres@1.0.0"
  - ${PG_RO_URL}  # Connection string from environment
description: Read-only PostgreSQL database access
scopes:
  - read:tables
limits:
  rate_per_min: 120
  timeout_s: 30
```

**Environment Setup:**
```bash
export PG_RO_URL="postgresql://readonly:password@localhost/agdd"
```

**Available Tools:**
- `query_table(table, filters)`: Query table data
- `describe_table(table)`: Get schema information
- `list_tables()`: List available tables
- `execute_query(sql)`: Run read-only SQL (SELECT only)

**Security:**
- Read-only access enforced at database level
- No DDL/DML operations (INSERT, UPDATE, DELETE)
- Requires `PG_RO_URL` environment variable

## Using MCP in Agents

### Implicit Tool Usage

LLM runtimes automatically expose MCP tools to agents. Agents use natural language to invoke tools:

```python
# catalog/agents/main/code-review-mag/code/orchestrator.py

def run(payload: dict, **deps) -> dict:
    """Code review agent with Git MCP integration"""
    obs = deps['obs']

    # The LLM will automatically use git tools when instructed
    prompt = f"""
    Review the changes in the pull request #{payload['pr_number']}.

    Use git tools to:
    1. Get the diff for the PR
    2. Analyze changed files
    3. Check commit messages
    4. Identify potential issues

    Return a structured review with findings and recommendations.
    """

    obs.log("start_review", {"pr": payload['pr_number']})

    # The LLM invokes git_diff(), git_show(), etc. automatically
    result = deps['skills'].invoke(
        "skill.code-review",
        {"prompt": prompt, "pr_number": payload['pr_number']}
    )

    return result
```

### Explicit Tool Calling

For programmatic control, agents can request specific tools:

```python
def run(payload: dict, **deps) -> dict:
    """Agent with explicit MCP tool usage"""
    skills = deps['skills']

    # Request filesystem tool explicitly
    result = skills.invoke(
        "skill.file-analysis",
        payload,
        tools=[
            {"type": "mcp", "server": "filesystem", "tool": "read_file"},
            {"type": "mcp", "server": "filesystem", "tool": "search_files"}
        ]
    )

    return result
```

## MCP Call Tracking

All MCP invocations are logged for observability and cost tracking.

### MCP Logs Format

```jsonl
# .runs/agents/<RUN_ID>/mcp_calls.jsonl
{"ts": "2024-01-15T10:30:00Z", "server": "filesystem", "tool": "read_file", "args": {"path": "README.md"}, "status": "ok", "duration_ms": 45}
{"ts": "2024-01-15T10:30:01Z", "server": "git", "tool": "git_diff", "args": {"ref": "HEAD~1"}, "status": "ok", "duration_ms": 120}
{"ts": "2024-01-15T10:30:02Z", "server": "memory", "tool": "query_entities", "args": {"type": "user"}, "status": "error", "error": "Rate limit exceeded"}
```

### Analyzing MCP Usage

```bash
# Count MCP calls per server
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq -r '.server' | sort | uniq -c

# Find failed MCP calls
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq 'select(.status != "ok")'

# Calculate average latency per tool
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq -r '"\(.tool) \(.duration_ms)"' | \
  awk '{sum[$1]+=$2; count[$1]++} END {for (tool in sum) print tool, sum[tool]/count[tool]}'
```

### Summary Statistics

```bash
# View MCP stats in run summary
uv run agdd flow summarize --output summary.json
cat summary.json | jq '.mcp_stats'

# Example output:
{
  "total_calls": 45,
  "total_errors": 2,
  "calls_by_server": {
    "filesystem": 20,
    "git": 15,
    "memory": 10
  },
  "error_rate": 0.044
}
```

## Custom MCP Servers

### Creating a Custom Server

Create a new MCP server configuration:

```yaml
# .mcp/servers/custom-api.yaml
server_id: custom-api
type: mcp
command: npx
args:
  - -y
  - "@myorg/mcp-server-custom@1.0.0"
  - --api-key
  - ${CUSTOM_API_KEY}
description: Custom API integration
scopes:
  - read:api
  - write:api
limits:
  rate_per_min: 60
  timeout_s: 30
```

**Environment Variables:**
```bash
export CUSTOM_API_KEY="your-api-key"
```

### Implementing Server Logic

```javascript
// packages/mcp-server-custom/src/index.js
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server({
  name: "custom-api",
  version: "1.0.0"
}, {
  capabilities: {
    tools: {}
  }
});

// Define tools
server.setRequestHandler("tools/list", async () => {
  return {
    tools: [
      {
        name: "fetch_data",
        description: "Fetch data from custom API",
        inputSchema: {
          type: "object",
          properties: {
            endpoint: { type: "string" },
            params: { type: "object" }
          },
          required: ["endpoint"]
        }
      }
    ]
  };
});

// Handle tool invocations
server.setRequestHandler("tools/call", async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "fetch_data") {
    const response = await fetch(
      `${process.env.CUSTOM_API_BASE_URL}/${args.endpoint}`,
      {
        headers: {
          "Authorization": `Bearer ${process.env.CUSTOM_API_KEY}`
        }
      }
    );
    return { content: [{ type: "text", text: await response.text() }] };
  }

  throw new Error(`Unknown tool: ${name}`);
});

// Start server
const transport = new StdioServerTransport();
await server.connect(transport);
```

### Registering Custom Server

```bash
# Install custom server
npm install @myorg/mcp-server-custom

# Verify server is available
npx @myorg/mcp-server-custom --help

# Test server
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | \
  npx @myorg/mcp-server-custom
```

## Rate Limiting and Quotas

### Per-Server Limits

Rate limits are defined in the `limits` section of each server configuration:

```yaml
# .mcp/servers/filesystem.yaml
limits:
  rate_per_min: 60      # Maximum 60 requests per minute
  timeout_s: 30         # 30 second timeout per request
```

**Configured Limits:**
- Filesystem: 60 requests/min, 30s timeout
- Git: 30 requests/min, 60s timeout
- Memory: 120 requests/min, 20s timeout
- Fetch: 30 requests/min, 30s timeout
- PostgreSQL: 120 requests/min, 30s timeout

### Handling Rate Limits

```python
def robust_mcp_invoke(skill_id: str, payload: dict, skills, obs, max_retries: int = 3):
    """Invoke skill with MCP, retry on rate limit"""
    import time

    for attempt in range(max_retries):
        try:
            return skills.invoke(skill_id, payload)
        except McpRateLimitError as e:
            if attempt == max_retries - 1:
                raise

            wait_time = 2 ** attempt  # Exponential backoff
            obs.log("mcp_rate_limit", {
                "server": e.server,
                "retry_attempt": attempt + 1,
                "wait_time": wait_time
            })
            time.sleep(wait_time)
```

### Monitoring Rate Limits

```bash
# Check rate limit errors
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq 'select(.status == "error" and (.error | contains("rate limit")))'

# Count rate limit errors by server
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq 'select(.status == "error" and (.error | contains("rate limit")))' | \
  jq -r '.server' | sort | uniq -c
```

## Security Best Practices

### 1. Principle of Least Privilege

Only grant necessary scopes:

```yaml
# BAD: Overly permissive
scopes:
  - read:files
  - write:files
  - execute:commands  # Dangerous!

# GOOD: Minimal scopes
scopes:
  - read:files  # Only what's needed
```

### Path Restrictions

Restrict filesystem access:

```yaml
# .mcp/servers/filesystem.yaml
server_id: filesystem
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-filesystem@2025.8.21"
  - "./docs"  # Restrict to docs directory only
description: Filesystem access restricted to documentation
scopes:
  - read:files  # Read-only, no write scope
limits:
  rate_per_min: 60
  timeout_s: 30
```

**Security Notes:**
- The path argument restricts server access to specified directory
- Omitting `write:files` scope makes it read-only
- Server cannot access parent directories (e.g., `../`)

### 3. Environment Variable Protection

Use environment variables for secrets:

```yaml
# .mcp/servers/pg-readonly.yaml
server_id: pg-readonly
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-postgres@1.0.0"
  - ${PG_RO_URL}  # Environment variable, not hardcoded!
description: Read-only database access
scopes:
  - read:tables
limits:
  rate_per_min: 120
  timeout_s: 30
```

```bash
# .env
PG_RO_URL="postgresql://readonly:***@localhost/agdd"
```

### 4. Read-Only Access

Prefer read-only servers for safety:

```yaml
# Read-only database access
server_id: pg-readonly
type: mcp
command: npx
args:
  - -y
  - "@modelcontextprotocol/server-postgres@1.0.0"
  - ${PG_RO_URL}
scopes:
  - read:tables  # No write scope!
limits:
  rate_per_min: 120
  timeout_s: 30
```

### 5. Audit Logging

Monitor MCP usage for security incidents:

```bash
# Detect suspicious filesystem access
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq 'select(.server == "filesystem" and (.args.path | contains("..")))'

# Monitor privileged operations
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq 'select(.tool | test("write|delete|execute"))'
```

## Performance Optimization

### 1. Minimize MCP Calls

Batch operations when possible:

```python
# Inefficient: N calls
for file in files:
    content = mcp.read_file(file)
    process(content)

# Efficient: Use batch operations or aggregation
all_files = mcp.list_directory("src/")
relevant_files = [f for f in all_files if f.endswith(".py")]
# Process in bulk
```

### 2. Cache MCP Results

Avoid redundant calls:

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_mcp_call(server: str, tool: str, args_hash: str):
    """Cache MCP results for repeated calls"""
    return skills.invoke("skill.mcp-call", {
        "server": server,
        "tool": tool,
        "args": json.loads(args_hash)
    })
```

### 3. Parallel MCP Calls

Use async for concurrent calls:

```python
import asyncio

async def parallel_file_reads(files: list[str]) -> list[str]:
    """Read multiple files concurrently"""
    tasks = [read_file_async(f) for f in files]
    return await asyncio.gather(*tasks)
```

## Troubleshooting

### Server Not Available

```bash
# Check server installation
npx @modelcontextprotocol/server-filesystem --version

# Test server connectivity
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | \
  npx @modelcontextprotocol/server-filesystem

# Verify configuration
cat .mcp/servers/filesystem.yaml
```

### Rate Limit Errors

```bash
# Identify rate limit issues
grep -r "rate limit" .runs/agents/<RUN_ID>/

# Increase rate limits
vim .mcp/servers/filesystem.yaml
# Update rate_limit: 120  # Doubled
```

### Permission Denied

```bash
# Check file permissions
ls -la <file-path>

# Verify server scope configuration
cat .mcp/servers/filesystem.yaml | grep scopes

# Check path restrictions
cat .mcp/servers/filesystem.yaml | grep -A5 config
```

### High Latency

```bash
# Analyze MCP call latency
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq 'select(.duration_ms > 1000)'  # Calls over 1 second

# Identify slow tools
cat .runs/agents/<RUN_ID>/mcp_calls.jsonl | \
  jq -r '"\(.tool) \(.duration_ms)"' | \
  sort -k2 -n | tail -10
```

## Examples

### Example 1: File Analysis Agent

```python
# catalog/agents/sub/file-analyzer-sag/code/advisor.py

def run(payload: dict, **deps) -> dict:
    """Analyze files using filesystem MCP"""
    obs = deps['obs']
    obs.log("start", {"files": payload["files"]})

    # LLM automatically uses filesystem MCP tools
    prompt = f"""
    Analyze the following files:
    {', '.join(payload['files'])}

    For each file:
    1. Read the content
    2. Identify the file type and purpose
    3. Count lines of code
    4. List dependencies
    5. Detect potential issues

    Use filesystem MCP tools to read and analyze files.
    """

    result = deps['skills'].invoke("skill.file-analysis", {"prompt": prompt})

    obs.log("complete", {"analyzed": len(payload['files'])})
    return result
```

### Example 2: Git History Agent

```python
# catalog/agents/sub/git-history-sag/code/advisor.py

def run(payload: dict, **deps) -> dict:
    """Analyze git history using git MCP"""
    obs = deps['obs']

    prompt = f"""
    Analyze git history for file: {payload['file_path']}

    Tasks:
    1. Get commit history (last 50 commits)
    2. Identify main contributors
    3. Detect patterns (frequency, size of changes)
    4. Find related files (often changed together)

    Use git MCP tools for analysis.
    """

    result = deps['skills'].invoke("skill.git-analysis", {"prompt": prompt})

    obs.log("complete", {"file": payload['file_path']})
    return result
```

### Example 3: Knowledge Base Agent

```python
# catalog/agents/main/kb-builder-mag/code/orchestrator.py

def run(payload: dict, **deps) -> dict:
    """Build knowledge base using memory MCP"""
    obs = deps['obs']

    prompt = f"""
    Build a knowledge base from the provided documents.

    Steps:
    1. Extract entities (people, places, concepts)
    2. Create entities in memory MCP
    3. Identify relationships between entities
    4. Create relations in memory MCP
    5. Return knowledge graph summary

    Documents: {payload['documents']}
    """

    result = deps['skills'].invoke("skill.kb-construction", {"prompt": prompt})

    obs.log("complete", {"entities": result.get("entity_count", 0)})
    return result
```

## Related Documentation

- [Agent Development Guide](./agent-development.md) - Building MCP-enabled agents
- [Multi-Provider Guide](./multi-provider.md) - LLM provider configuration
- [Cost Optimization](./cost-optimization.md) - Managing MCP call costs
- [Storage Layer](../storage.md) - Querying MCP usage data

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Reference Servers](https://github.com/modelcontextprotocol/servers)
- [MCP SDK Documentation](https://github.com/modelcontextprotocol/sdk)
- [Security Best Practices](https://modelcontextprotocol.io/docs/security)
