# Model Context Protocol (MCP) Server Configuration

This directory contains MCP server configurations for the MAGSAG framework.

## Available Servers

### Filesystem (`filesystem.yaml`)
Secure file operations with configurable access controls.
- **Version**: @modelcontextprotocol/server-filesystem@2025.8.21
- **Scopes**: read:files, write:files
- **Repository Path**: Current working directory (`.`)
- **Note**: Run from repository root for proper operation

### Git (`git.yaml`)
Tools to read, search, and manipulate Git repositories.
- **Version**: @modelcontextprotocol/server-git@1.0.0
- **Scopes**: read:git, write:git
- **Repository Path**: Current working directory (`.`)
- **Note**: Run from repository root for proper operation

### Memory (`memory.yaml`)
Knowledge graph-based persistent memory system.
- **Version**: @modelcontextprotocol/server-memory@2025.9.25
- **Scopes**: read:memory, write:memory

### Fetch (`fetch.yaml`)
Web content fetching and conversion for efficient LLM usage.
- **Version**: @modelcontextprotocol/server-fetch@1.0.0
- **Scopes**: read:web

### PostgreSQL Read-Only (`pg-readonly.yaml`)
Read-only PostgreSQL database access.
- **Scopes**: read:tables
- **Connection**: Via PG_RO_URL environment variable

## Usage

These MCP servers are automatically available to agents running within the MAGSAG framework. The servers are invoked via npx and use the official Model Context Protocol SDKs.

**Important**: MCP servers using filesystem or git configurations must be run from the repository root directory. The configurations use relative paths (`.`) to ensure portability across different environments and user setups.

## Rate Limits

Each server has configured rate limits to prevent abuse:
- Filesystem: 60 requests/min
- Git: 30 requests/min
- Memory: 120 requests/min
- Fetch: 30 requests/min
- PostgreSQL: 120 requests/min

## Environment Variables

- `PG_RO_URL`: PostgreSQL read-only connection string (required for pg-readonly server)

## Version Management

All MCP server packages are pinned to specific versions to ensure:
- **Deterministic behavior**: Same package version runs across all environments
- **Security**: Protection against supply-chain attacks from compromised future releases
- **Stability**: Prevents unexpected breaking changes from automatic updates

To update MCP server versions:
1. Check for new versions: `npm view @modelcontextprotocol/server-<name> version`
2. Update the version in the corresponding `.yaml` file
3. Test the new version in a development environment
4. Commit the version update with a clear changelog entry

## References

- [MCP Official Documentation](https://modelcontextprotocol.io/)
- [MCP Reference Servers](https://github.com/modelcontextprotocol/servers)
