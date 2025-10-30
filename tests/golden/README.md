# Golden Tests

This directory contains golden test cases for AGDD agents. Golden tests verify that agents produce expected outputs for known inputs, enabling regression detection and behavior validation.

## Overview

Golden tests serve as reference implementations and regression tests for agent behavior. Each test case consists of:

- **Input data**: The test input provided to the agent
- **Expected output**: The expected result from the agent
- **Test metadata**: Additional information about the test case

**Note**: The current benchmark harness uses a dummy implementation (no real LLM calls). The `sample_agent` test is expected to fail with the dummy implementation to demonstrate that the comparison logic works correctly. When integrating real agent execution, update the harness to invoke actual agents and the golden tests will properly validate outputs.

## Directory Structure

Each golden test case is organized as a directory with the following structure:

```
tests/golden/
├── README.md                    # This file
├── sample_agent/                # Example test case
│   ├── input.json              # Input data for the agent
│   └── expected/
│       └── output.json         # Expected output from the agent
└── {agent_name}/               # Additional test cases
    ├── input.json
    └── expected/
        └── output.json
```

## File Formats

### input.json

The `input.json` file contains the input data that will be provided to the agent:

```json
{
  "payload": {
    "field1": "value1",
    "field2": "value2"
  }
}
```

### expected/output.json

The `expected/output.json` file contains the expected output from the agent:

```json
{
  "result": "expected result",
  "status": "success",
  "data": {
    "key": "value"
  }
}
```

## Running Golden Tests

### Using the Benchmark Harness

The benchmark harness automatically discovers and runs all golden tests:

```bash
python benchmarks/harness.py
```

Or using Make:

```bash
make bench
```

### Using pytest

Golden tests can be integrated into the pytest suite:

```bash
pytest tests/golden/ -v
```

## Creating New Golden Tests

To create a new golden test case:

1. Create a new directory under `tests/golden/` with the agent name:
   ```bash
   mkdir -p tests/golden/my_agent/expected
   ```

2. Create `input.json` with the test input:
   ```bash
   cat > tests/golden/my_agent/input.json << 'EOF'
   {
     "payload": {
       "test": "data"
     }
   }
   EOF
   ```

3. Create `expected/output.json` with the expected output:
   ```bash
   cat > tests/golden/my_agent/expected/output.json << 'EOF'
   {
     "result": "expected"
   }
   EOF
   ```

4. Run the test to verify:
   ```bash
   python benchmarks/harness.py
   ```

## Test Guidelines

### Input Data

- Use realistic, representative inputs
- Include edge cases and boundary conditions
- Document any special requirements in comments
- Keep inputs focused and minimal

### Expected Outputs

- Be specific and precise
- Include all relevant fields
- Document any acceptable variations
- Use deterministic values where possible

### Test Naming

- Use descriptive directory names: `{agent_name}` or `{agent_name}_{scenario}`
- Examples:
  - `offer_orchestrator_basic`
  - `compensation_advisor_edge_case`
  - `router_fallback_scenario`

## Deterministic Testing

For reproducible tests:

- Use fixed seeds and parameters in test configurations
- Set `temperature=0` for deterministic model outputs
- Document any non-deterministic behavior
- Consider using `--deterministic` flag when available

## Validation

Golden tests are validated by:

1. **Structure validation**: Ensuring all required files exist
2. **Schema validation**: Verifying JSON structure and types
3. **Output comparison**: Comparing actual vs. expected outputs using deep comparison
   - Compares nested dictionaries and lists recursively
   - Reports specific differences (missing keys, type mismatches, value differences)
   - Marks tests as failed if outputs don't match
4. **Regression detection**: Alerting on unexpected changes

### Output Comparison Details

The harness performs deep comparison of actual vs. expected outputs:

- **Dictionary comparison**: Checks for missing/extra keys and recursively compares values
- **List comparison**: Validates length and compares elements in order
- **Type checking**: Ensures types match (e.g., string vs. int)
- **Value equality**: Uses exact equality for primitives

When a mismatch is detected, the test fails and the error message includes:
- The location of the difference (e.g., key name, list index)
- The type of mismatch (missing key, value difference, type error)
- The expected vs. actual values

## Integration with CI/CD

Golden tests run automatically in CI:

- On every pull request
- On merge to main branches
- As part of the test suite gates

## Troubleshooting

### Test Not Found

If the benchmark harness doesn't find your test:

- Verify the directory structure matches the expected layout
- Ensure `input.json` exists and is valid JSON
- Check file permissions

### Output Mismatch

If actual output doesn't match expected:

- Review the diff to understand the change
- Determine if the change is intentional (update expected output)
- Investigate if the change represents a regression (fix the agent)

### Non-Deterministic Results

If tests produce varying results:

- Check for random seeds or temperature settings
- Review for external dependencies (time, randomness)
- Consider using deterministic mode or mocking

## Future Enhancements

Planned improvements to the golden test framework:

- [ ] Fuzzy matching for outputs with tolerance
- [ ] Automatic generation of test cases from runs
- [ ] Performance benchmarking integration
- [ ] Multi-turn conversation testing
- [ ] Tool call verification
- [ ] Cost and latency tracking

## References

- [AGDD Architecture Documentation](../../docs/architecture/)
- [Benchmark Harness](../../benchmarks/harness.py)
- [PLANS.md WS-11](../../PLANS.md)

## Contributing

When adding golden tests:

1. Follow the directory structure conventions
2. Include clear, representative test cases
3. Document any special requirements
4. Update this README if adding new patterns
5. Ensure tests pass in CI before merging

---

For questions or issues with golden tests, please refer to the main project documentation or open an issue.
