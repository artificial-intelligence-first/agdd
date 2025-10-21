# Refactor: Improve code quality and add MCP configurations

## Summary

This PR addresses several code quality issues identified during a comprehensive code review of the AGDD framework, ensures full English language consistency, and adds official Model Context Protocol server configurations. All changes improve maintainability, robustness, and code clarity while maintaining backward compatibility.

## Changes

### High Priority Fixes

1. **Fixed variable shadowing in `observability/summarize_runs.py`** (L261, L329)
   - Renamed `summary` variable to `run_summary` in the loop to avoid shadowing the final return value
   - Improves code clarity and prevents potential bugs

2. **Improved CLI argument design in `agdd/cli.py`** (L87)
   - Changed `text` parameter from positional with default to explicit `typer.Option`
   - Provides better help text and more intuitive CLI usage
   - Maintains backward compatibility with existing tests

3. **Removed unnecessary `idna` dependency from `pyproject.toml`** (L13)
   - The dependency was not directly used in the codebase
   - Reduces package footprint and dependency complexity

### Medium Priority Improvements

4. **Enhanced error handling in `agdd/runners/flowrunner.py`** (L46)
   - Added 300-second timeout to subprocess calls
   - Added graceful handling for `TimeoutExpired` and `FileNotFoundError` exceptions
   - Returns structured error messages instead of crashing

5. **Improved wildcard pattern matching in `agdd/governance/gate.py`** (L37)
   - Replaced simple string matching with `fnmatch.fnmatch()` for proper glob-style patterns
   - Now supports patterns like `*-experimental`, `model-*-test`, etc.
   - More flexible and robust pattern matching

### Documentation & Code Quality

6. **Added comprehensive docstrings**
   - `_extract_model()`: Documents model extraction logic from various record locations
   - `_classify_error()`: Explains error classification patterns
   - `_match_pattern()`: Documents glob-style wildcard matching

7. **Added clarifying comments**
   - MCP metrics fallback logic in `summarize_runs.py` (L308)
   - Explains why we aggregate from steps when not directly provided

### Testing

8. **Added 7 new tests** (30 total tests now passing)
   - `tests/runner/test_flowrunner_errors.py`: Tests error handling for unavailable flowctl
   - `tests/governance/test_gate_patterns.py`: Tests wildcard pattern matching scenarios
   - All existing tests continue to pass

### Language Consistency

9. **Translated Japanese section in PLANS.md to English**
   - Converted "最新タスク" section to "Recent Tasks"
   - Repository now 100% English across all documentation and code
   - Improves accessibility for international contributors

### Infrastructure & Configuration

10. **Added official MCP server configurations**
   - `filesystem.yaml`: Secure file operations with access controls
   - `git.yaml`: Repository read, search, and manipulation tools
   - `memory.yaml`: Knowledge graph-based persistent memory system
   - `fetch.yaml`: Web content fetching and conversion
   - Added `.mcp/README.md` documenting all servers, scopes, and rate limits
   - Provides essential capabilities for AI agents in AGDD framework

## Testing

```bash
$ uv run -m pytest -q
..............................                                           [100%]
30 passed in 0.5s
```

## Files Changed

**Code Quality:**
- `agdd/cli.py`: Improved CLI argument design
- `agdd/governance/gate.py`: Enhanced wildcard pattern matching
- `agdd/runners/flowrunner.py`: Added error handling and timeout
- `observability/summarize_runs.py`: Fixed variable shadowing, added docstrings
- `pyproject.toml`: Removed unused idna dependency
- `uv.lock`: Updated lock file

**Testing:**
- `tests/governance/test_gate_patterns.py`: New tests for pattern matching
- `tests/runner/test_flowrunner_errors.py`: New tests for error handling

**Documentation:**
- `PLANS.md`: Translated Japanese section to English
- `PR_DESCRIPTION.md`: This file

**Configuration:**
- `.mcp/README.md`: MCP server documentation
- `.mcp/servers/filesystem.yaml`: Filesystem MCP server config
- `.mcp/servers/git.yaml`: Git MCP server config
- `.mcp/servers/memory.yaml`: Memory MCP server config
- `.mcp/servers/fetch.yaml`: Fetch MCP server config

## Breaking Changes

None. All changes are backward compatible.

## Checklist

- [x] All tests pass (30 tests)
- [x] Code follows project style guidelines
- [x] Documentation updated where necessary
- [x] No breaking changes introduced
- [x] Dependency changes verified (removed unused `idna`)

## Review Priority

**Critical for merge:**
- Variable shadowing fix (prevents potential bugs)
- Error handling improvements (prevents crashes)

**Important but non-critical:**
- CLI argument design (improves UX)
- Pattern matching improvements (more flexible)
- Dependency cleanup (reduces footprint)

**Nice to have:**
- Documentation improvements
- Additional test coverage

---

Generated with Claude Code (https://claude.com/claude-code)
