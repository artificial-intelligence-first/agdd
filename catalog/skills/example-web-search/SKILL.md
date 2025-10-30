---
name: example-web-search
description: >
  Example MCP tool wrapper for web content fetching and search.
  Demonstrates how to integrate the fetch MCP server for web search capabilities.
iface:
  input_schema: contracts/web_search_query.schema.json
  output_schema: contracts/web_search_result.schema.json
mcp:
  server_ref: "fetch"
slo:
  success_rate_min: 0.95
  latency_p95_ms: 3000
limits:
  rate_per_min: 30
---

# Example Web Search (example-web-search)

## Purpose
Demonstrates integration with the fetch MCP server to retrieve and process web content. This example shows how to wrap an MCP tool for web search/fetch operations, including URL fetching, content extraction, and result formatting.

## When to Use
- Need to fetch content from a web URL
- Require web search capabilities in an agent workflow
- Want to integrate external web data into skill processing
- Building workflows that combine web data with other skills

## Prerequisites
- The `fetch` MCP server must be configured in `.mcp/servers/fetch.yaml`
- Internet connectivity for accessing web resources
- Input conforms to `contracts/web_search_query.schema.json`
- Rate limits configured to respect web service constraints

## Procedures

### Procedure 1: Fetch Web Content
1. **Validate Input** - Ensure the query payload includes a valid URL or search query
2. **Prepare Fetch Request** - Extract URL and optional parameters (user agent, headers, etc.)
3. **Call Fetch Tool** - Invoke the fetch MCP server to retrieve web content
4. **Extract Content** - Parse the returned HTML/text and extract relevant information
5. **Format Results** - Transform raw content into structured output matching the schema
6. **Validate Output** - Ensure the result conforms to the output contract

### Procedure 2: Error Handling
1. Handle HTTP errors (404, 500, etc.) gracefully
2. Manage timeouts and network failures
3. Return partial results when available
4. Log failures with sufficient context for debugging

## Examples

### Example 1: Fetch URL Content
- **Input**: [resources/examples/in.json](resources/examples/in.json)
  ```json
  {
    "url": "https://example.com",
    "extract_text": true
  }
  ```
- **Process**:
  1. Validate URL format
  2. Call fetch MCP tool with URL
  3. Extract text content from HTML
  4. Format as structured result
- **Output**: [resources/examples/out.json](resources/examples/out.json)
  ```json
  {
    "url": "https://example.com",
    "title": "Example Domain",
    "content": "This domain is for use in illustrative examples...",
    "metadata": {
      "status_code": 200,
      "content_type": "text/html"
    }
  }
  ```

## Implementation Notes

### MCP Server Integration
This skill uses the `fetch` MCP server configured in `.mcp/servers/fetch.yaml`. The fetch server provides tools for:
- Fetching web content from URLs
- Converting HTML to markdown or plain text
- Handling redirects and error responses
- Respecting robots.txt and rate limits

### Rate Limiting
The skill is configured with a rate limit of 30 requests/minute to avoid overwhelming external web services and to respect the MCP server's capacity.

### Content Processing
The implementation demonstrates:
- URL validation
- HTML content extraction
- Text normalization
- Metadata extraction (status codes, content types, etc.)

## Additional Resources
- `.mcp/servers/fetch.yaml` - Fetch MCP server configuration
- MCP Fetch Server Documentation: https://github.com/modelcontextprotocol/servers/tree/main/src/fetch
- `catalog/skills/_template/mcp-tool-template/` - Template for creating new MCP tools

## Troubleshooting
- **URL Not Accessible**: Verify the URL is reachable and not behind a firewall
- **Rate Limit Errors**: Reduce request frequency or increase rate limit in configuration
- **Content Extraction Failures**: Check if the target website has changed its HTML structure
- **MCP Server Not Available**: Ensure fetch server is configured in `.mcp/servers/fetch.yaml`
- **Timeout Errors**: Increase latency threshold for slow websites
