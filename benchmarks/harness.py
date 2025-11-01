"""Minimal benchmark harness for MAGSAG agents.

This module provides a simple benchmark runner for evaluating agent performance
across quality, cost, and latency dimensions. It supports running golden tests
and generating reports in HTML and Markdown formats.

Usage:
    python benchmarks/harness.py
    make bench

Exit Status:
    0 - All tests passed
    1 - One or more tests failed (for CI/CD integration)
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _compare_outputs(actual: Any, expected: Any) -> tuple[bool, str | None]:
    """Compare actual output with expected output.

    Args:
        actual: The actual output from the agent
        expected: The expected output to compare against

    Returns:
        Tuple of (matches, diff_message)
        - matches: True if outputs match, False otherwise
        - diff_message: Description of differences if they don't match, None if they match
    """
    if actual == expected:
        return True, None

    # Generate a helpful diff message
    if type(actual) is not type(expected):
        return False, f"Type mismatch: expected {type(expected).__name__}, got {type(actual).__name__}"

    if isinstance(actual, dict):
        expected_keys = set(expected.keys())
        actual_keys = set(actual.keys())

        missing_keys = expected_keys - actual_keys
        extra_keys = actual_keys - expected_keys

        if missing_keys or extra_keys:
            parts = []
            if missing_keys:
                parts.append(f"missing keys: {sorted(missing_keys)}")
            if extra_keys:
                parts.append(f"extra keys: {sorted(extra_keys)}")
            return False, f"Key mismatch - {', '.join(parts)}"

        # Check values for matching keys
        for key in expected_keys:
            matches, diff = _compare_outputs(actual[key], expected[key])
            if not matches:
                return False, f"Difference in key '{key}': {diff}"

        return True, None

    elif isinstance(actual, list):
        if len(actual) != len(expected):
            return False, f"List length mismatch: expected {len(expected)}, got {len(actual)}"

        for i, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            matches, diff = _compare_outputs(actual_item, expected_item)
            if not matches:
                return False, f"Difference at index {i}: {diff}"

        return True, None

    else:
        return False, f"Value mismatch: expected {expected!r}, got {actual!r}"


@dataclass
class BenchResult:
    """Result of a single benchmark run.

    Attributes:
        agent: Name of the agent being benchmarked
        input_data: Input data provided to the agent
        output_data: Output data returned by the agent
        duration_ms: Execution time in milliseconds
        success: Whether the benchmark run succeeded
        error: Error message if the run failed
        metadata: Additional metadata about the run
    """
    agent: str
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None = None
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BenchRunner:
    """Minimal benchmark runner for MAGSAG agents.

    This runner executes benchmark tests against agents and collects performance
    metrics. Currently uses dummy measurements without real LLM calls.
    """

    def __init__(self) -> None:
        """Initialize the benchmark runner."""
        self.results: list[BenchResult] = []

    def run_benchmark(
        self,
        agent: str,
        input_data: dict[str, Any],
    ) -> BenchResult:
        """Run a benchmark test against an agent.

        Args:
            agent: Name of the agent to benchmark
            input_data: Input data to provide to the agent

        Returns:
            BenchResult containing the benchmark metrics
        """
        start_time = time.time()

        try:
            # Dummy implementation - no real LLM call
            # In a real implementation, this would invoke the agent
            output_data = {
                "result": f"Processed input for {agent}",
                "agent": agent,
                "echo": input_data,
            }

            duration_ms = (time.time() - start_time) * 1000

            result = BenchResult(
                agent=agent,
                input_data=input_data,
                output_data=output_data,
                duration_ms=duration_ms,
                success=True,
                metadata={
                    "timestamp": time.time(),
                    "harness_version": "0.1.0",
                },
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            result = BenchResult(
                agent=agent,
                input_data=input_data,
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )

        self.results.append(result)
        return result

    def generate_report(
        self,
        results: list[BenchResult] | None = None,
        format: str = "markdown",
    ) -> str:
        """Generate a report from benchmark results.

        Args:
            results: List of benchmark results. If None, uses all collected results.
            format: Output format, either "markdown" or "html"

        Returns:
            Formatted report as a string
        """
        if results is None:
            results = self.results

        if not results:
            return "No benchmark results available."

        if format == "html":
            return self._generate_html_report(results)
        else:
            return self._generate_markdown_report(results)

    def _generate_markdown_report(self, results: list[BenchResult]) -> str:
        """Generate a Markdown report.

        Args:
            results: List of benchmark results

        Returns:
            Markdown-formatted report
        """
        lines = [
            "# Benchmark Report",
            "",
            f"Total runs: {len(results)}",
            f"Successful: {sum(1 for r in results if r.success)}",
            f"Failed: {sum(1 for r in results if not r.success)}",
            "",
            "## Results",
            "",
            "| Agent | Duration (ms) | Success | Error |",
            "|-------|---------------|---------|-------|",
        ]

        for result in results:
            error = result.error or "-"
            lines.append(
                f"| {result.agent} | {result.duration_ms:.2f} | "
                f"{'✓' if result.success else '✗'} | {error} |"
            )

        lines.extend([
            "",
            "## Summary Statistics",
            "",
        ])

        successful_results = [r for r in results if r.success]
        if successful_results:
            avg_duration = sum(r.duration_ms for r in successful_results) / len(successful_results)
            min_duration = min(r.duration_ms for r in successful_results)
            max_duration = max(r.duration_ms for r in successful_results)

            lines.extend([
                f"- Average duration: {avg_duration:.2f} ms",
                f"- Min duration: {min_duration:.2f} ms",
                f"- Max duration: {max_duration:.2f} ms",
            ])

        return "\n".join(lines)

    def _generate_html_report(self, results: list[BenchResult]) -> str:
        """Generate an HTML report.

        Args:
            results: List of benchmark results

        Returns:
            HTML-formatted report
        """
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count

        rows = []
        for result in results:
            success_class = "success" if result.success else "failure"
            error_cell = result.error or "-"
            rows.append(
                f'  <tr class="{success_class}">'
                f'<td>{result.agent}</td>'
                f'<td>{result.duration_ms:.2f}</td>'
                f'<td>{"✓" if result.success else "✗"}</td>'
                f'<td>{error_cell}</td></tr>'
            )

        table_rows = "\n".join(rows)

        successful_results = [r for r in results if r.success]
        stats_html = ""
        if successful_results:
            avg_duration = sum(r.duration_ms for r in successful_results) / len(successful_results)
            min_duration = min(r.duration_ms for r in successful_results)
            max_duration = max(r.duration_ms for r in successful_results)

            stats_html = f"""
<h2>Summary Statistics</h2>
<ul>
  <li>Average duration: {avg_duration:.2f} ms</li>
  <li>Min duration: {min_duration:.2f} ms</li>
  <li>Max duration: {max_duration:.2f} ms</li>
</ul>
"""

        html = f"""<!DOCTYPE html>
<html>
<head>
  <title>Benchmark Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    h1 {{ color: #333; }}
    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background-color: #f2f2f2; }}
    tr.success {{ background-color: #e8f5e9; }}
    tr.failure {{ background-color: #ffebee; }}
    .stats {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
  </style>
</head>
<body>
  <h1>Benchmark Report</h1>
  <div class="stats">
    <p><strong>Total runs:</strong> {len(results)}</p>
    <p><strong>Successful:</strong> {successful_count}</p>
    <p><strong>Failed:</strong> {failed_count}</p>
  </div>

  <h2>Results</h2>
  <table>
    <thead>
      <tr>
        <th>Agent</th>
        <th>Duration (ms)</th>
        <th>Success</th>
        <th>Error</th>
      </tr>
    </thead>
    <tbody>
{table_rows}
    </tbody>
  </table>

  {stats_html}
</body>
</html>
"""
        return html


def run_golden_tests(golden_dir: Path = Path("tests/golden")) -> list[BenchResult]:
    """Run all golden tests from the golden test directory.

    Args:
        golden_dir: Path to the golden tests directory

    Returns:
        List of benchmark results
    """
    runner = BenchRunner()
    results = []

    if not golden_dir.exists():
        print(f"Warning: Golden test directory not found: {golden_dir}")
        return results

    # Find all test cases (directories with input.json)
    for test_dir in golden_dir.iterdir():
        if not test_dir.is_dir():
            continue

        input_file = test_dir / "input.json"
        if not input_file.exists():
            continue

        agent_name = test_dir.name

        # Load input with error handling
        try:
            with input_file.open() as f:
                input_data = json.load(f)
        except json.JSONDecodeError as e:
            # Create a failed result for malformed input JSON
            result = BenchResult(
                agent=agent_name,
                input_data={},
                success=False,
                error=f"Invalid input JSON: {e.msg} at line {e.lineno} column {e.colno}",
            )
            results.append(result)
            print(f"✗ FAILED golden test: {agent_name} - Invalid input.json: {e.msg}")
            continue
        except Exception as e:
            # Handle other file reading errors
            result = BenchResult(
                agent=agent_name,
                input_data={},
                success=False,
                error=f"Error reading input.json: {str(e)}",
            )
            results.append(result)
            print(f"✗ FAILED golden test: {agent_name} - Error reading input.json: {e}")
            continue

        # Run benchmark
        result = runner.run_benchmark(agent_name, input_data)
        results.append(result)

        # Compare with expected output if available
        expected_file = test_dir / "expected" / "output.json"
        if expected_file.exists():
            try:
                with expected_file.open() as f:
                    expected_output = json.load(f)
            except json.JSONDecodeError as e:
                # Mark test as failed due to malformed expected JSON
                result.success = False
                result.error = f"Invalid expected output JSON: {e.msg} at line {e.lineno} column {e.colno}"
                result.metadata["has_expected"] = True
                result.metadata["expected_file"] = str(expected_file)
                print(f"✗ FAILED golden test: {agent_name} - Invalid expected/output.json: {e.msg}")
                continue
            except Exception as e:
                # Handle other file reading errors
                result.success = False
                result.error = f"Error reading expected output: {str(e)}"
                result.metadata["has_expected"] = True
                result.metadata["expected_file"] = str(expected_file)
                print(f"✗ FAILED golden test: {agent_name} - Error reading expected/output.json: {e}")
                continue

            result.metadata["has_expected"] = True
            result.metadata["expected_file"] = str(expected_file)

            # Compare actual output with expected output
            matches, diff_message = _compare_outputs(result.output_data, expected_output)
            if not matches:
                result.success = False
                result.error = f"Golden test output mismatch: {diff_message}"
                result.metadata["output_diff"] = diff_message
                print(f"✗ FAILED golden test: {agent_name} - {diff_message}")
            else:
                result.metadata["golden_match"] = True
                print(f"✓ Ran golden test: {agent_name} ({result.duration_ms:.2f}ms)")
        else:
            print(f"✓ Ran golden test: {agent_name} ({result.duration_ms:.2f}ms) [no expected output]")

    return results


def main() -> None:
    """Main entry point for the benchmark harness."""
    print("MAGSAG Benchmark Harness")
    print("=" * 50)
    print()

    # Example: Run a simple benchmark
    runner = BenchRunner()

    print("Running example benchmarks...")
    runner.run_benchmark(
        agent="example-agent",
        input_data={"task": "sample task", "mode": "test"},
    )
    runner.run_benchmark(
        agent="another-agent",
        input_data={"query": "benchmark query"},
    )

    print()
    print("Running golden tests...")
    golden_results = run_golden_tests()
    runner.results.extend(golden_results)

    print()
    print("=" * 50)
    print("Markdown Report:")
    print("=" * 50)
    print(runner.generate_report(format="markdown"))

    print()
    print("=" * 50)
    print("HTML Report (preview):")
    print("=" * 50)
    html_report = runner.generate_report(format="html")
    print(f"Generated HTML report ({len(html_report)} bytes)")

    # Optionally save HTML report
    output_path = Path("benchmark_report.html")
    output_path.write_text(html_report)
    print(f"Saved HTML report to: {output_path}")

    # Check for failures and exit with appropriate status
    failed_results = [r for r in runner.results if not r.success]
    if failed_results:
        print()
        print("=" * 50)
        print(f"❌ FAILED: {len(failed_results)} test(s) failed")
        for result in failed_results:
            print(f"  - {result.agent}: {result.error}")
        print("=" * 50)
        sys.exit(1)
    else:
        print()
        print("=" * 50)
        print(f"✅ SUCCESS: All {len(runner.results)} test(s) passed")
        print("=" * 50)
        sys.exit(0)


if __name__ == "__main__":
    main()
