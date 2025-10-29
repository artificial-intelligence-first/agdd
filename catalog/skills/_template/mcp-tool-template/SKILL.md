---
name: <skill-name>
description: >
  MCP tool wrapper for <tool-purpose>. Replace this with your tool's description.
iface:
  input_schema: contracts/<input-contract>.json
  output_schema: contracts/<output-contract>.json
mcp:
  server_ref: "<mcp-server-id>"
slo:
  success_rate_min: 0.99
  latency_p95_ms: 1000
limits:
  rate_per_min: 60
---

# <Skill Display Name> (<skill-name>)

## Purpose
MCP Tool Template provides a standardized structure for creating skills that wrap Model Context Protocol (MCP) tools. This template demonstrates how to integrate external MCP servers into the AGDD framework while maintaining contract validation, error handling, and observability requirements.

## When to Use
- You need to integrate an external MCP tool as a reusable skill
- The MCP server is configured in `.mcp/servers/<server-id>.yaml`
- Input and output data structures are defined via JSON Schema contracts
- The tool will be invoked by agents or other orchestration workflows

## Prerequisites
- MCP server configured in `.mcp/servers/<server-id>.yaml` with appropriate scopes
- Input schema defined at `catalog/contracts/<input-contract>.json`
- Output schema defined at `catalog/contracts/<output-contract>.json`
- Environment variables required by the MCP server (if any) are set
- Rate limits configured in the MCP server configuration

## Procedures

### Procedure 1: Invoke MCP Tool
1. **Validate Input** - Ensure the input payload conforms to the input schema contract
2. **Prepare Request** - Extract relevant fields from the payload and format them for the MCP tool
3. **Call MCP Tool** - Invoke the MCP server tool with prepared arguments
4. **Handle Response** - Process the MCP tool response and transform it to match the output schema
5. **Error Handling** - Catch and handle common errors (rate limits, timeouts, validation failures)
6. **Validate Output** - Ensure the output conforms to the output schema contract

### Procedure 2: Fallback Behavior
1. If the MCP tool is unavailable, return a structured error response
2. Log the failure with appropriate context for debugging
3. Consider returning cached results if applicable
4. Emit warnings when operating in degraded mode

## Examples

### Example 1: Basic Tool Invocation
- **Input**: [resources/examples/in.json](resources/examples/in.json)
- **Process**:
  1. Validate input against schema
  2. Call MCP tool with extracted parameters
  3. Transform response to output format
  4. Validate output against schema
- **Output**: [resources/examples/out.json](resources/examples/out.json)

## Implementation Notes

### File Structure
```
<skill-name>/
├── SKILL.md                    # This file
├── impl/
│   └── mcp_tool.py            # Tool implementation
├── resources/
│   └── examples/
│       ├── in.json            # Sample input
│       └── out.json           # Sample output
└── tests/
    └── test_mcp_tool.py       # Unit tests
```

### Key Functions
- `async def run(payload: dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> dict[str, Any]` – Main entry point with optional MCP runtime
- `_validate(payload: dict[str, Any], schema: dict[str, Any], name: str) -> None` – Input/output validation helper
- `_prepare_request(payload: dict[str, Any]) -> dict[str, Any]` – Request transformation helper
- `async def _call_mcp_tool(**kwargs) -> Any` – Local or mocked execution path when MCP runtime is unavailable
- `async def _call_tool_via_runtime(mcp: MCPRuntime, request: dict[str, Any]) -> Any` – Preferred MCP runtime integration path
- `_process_response(raw_response: Any, payload: dict[str, Any]) -> dict[str, Any]` – Response normalization helper

### Development Checklist
- [ ] Copy template to `catalog/skills/<your-skill-name>/`
- [ ] Update `name`, `description`, and `mcp.server_ref` in SKILL.md frontmatter
- [ ] Define input/output contracts in `catalog/contracts/`
- [ ] Implement `_call_mcp_tool()` in `impl/mcp_tool.py`
- [ ] Create example payloads in `resources/examples/`
- [ ] Write tests in `tests/test_mcp_tool.py`
- [ ] Run `mypy --strict` and `ruff` to ensure code quality
- [ ] Run `pytest` to verify all tests pass
- [ ] Register skill in `catalog/registry/skills.yaml` if needed

## Additional Resources
- `.mcp/README.md` - MCP server configuration guide
- `docs/guides/agent-development.md` - Skill development guidelines
- MCP Official Documentation: https://modelcontextprotocol.io/

## Troubleshooting
- **MCP Server Not Found**: Verify the server is configured in `.mcp/servers/<server-id>.yaml`
- **Rate Limit Exceeded**: Check the `limits.rate_per_min` setting in SKILL.md and MCP server config
- **Schema Validation Errors**: Ensure contracts match actual payload structure
- **Timeout Errors**: Increase latency threshold or optimize MCP tool query
- **Missing Environment Variables**: Check MCP server requirements in `.env.example`
