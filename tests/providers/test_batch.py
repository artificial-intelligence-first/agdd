"""
Tests for Batch API integration.

Tests cover:
- Batch file creation
- Batch job submission
- Status tracking
- Result retrieval
- Cost savings calculation
- Both /v1/responses and /v1/chat/completions endpoints
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agdd.optimization.batch import (
    BatchAPIClient,
    BatchEndpoint,
    BatchRequest,
    BatchStatus,
    calculate_batch_savings,
    create_batch_client,
)

# Skip all tests if OPENAI_API_KEY is not set
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
)


@pytest.fixture
def batch_client() -> BatchAPIClient:
    """Create batch API client"""
    return create_batch_client()


@pytest.fixture
def sample_requests() -> list[BatchRequest]:
    """Create sample batch requests"""
    return [
        BatchRequest(
            custom_id="request-1",
            url=BatchEndpoint.RESPONSES,
            body={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Say hello."}],
                "temperature": 0.0,
            },
        ),
        BatchRequest(
            custom_id="request-2",
            url=BatchEndpoint.RESPONSES,
            body={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Say goodbye."}],
                "temperature": 0.0,
            },
        ),
    ]


class TestBatchRequest:
    """Test BatchRequest creation and serialization"""

    def test_create_request(self) -> None:
        """Test creating a batch request"""
        request = BatchRequest(
            custom_id="test-1",
            url=BatchEndpoint.RESPONSES,
            body={"model": "gpt-4o-mini", "messages": []},
        )

        assert request.custom_id == "test-1"
        assert request.url == BatchEndpoint.RESPONSES
        assert request.method == "POST"

    def test_jsonl_serialization(self) -> None:
        """Test JSONL serialization"""
        request = BatchRequest(
            custom_id="test-1",
            url=BatchEndpoint.RESPONSES,
            body={"model": "gpt-4o-mini"},
        )

        jsonl = request.to_jsonl()
        data = json.loads(jsonl)

        assert data["custom_id"] == "test-1"
        assert data["method"] == "POST"
        assert data["url"] == BatchEndpoint.RESPONSES
        assert data["body"]["model"] == "gpt-4o-mini"

    def test_chat_completions_endpoint(self) -> None:
        """Test using chat completions endpoint"""
        request = BatchRequest(
            custom_id="test-chat",
            url=BatchEndpoint.CHAT_COMPLETIONS,
            body={"model": "gpt-4o-mini", "messages": []},
        )

        assert request.url == BatchEndpoint.CHAT_COMPLETIONS


class TestBatchFileOperations:
    """Test batch file creation and upload"""

    def test_create_batch_file(
        self, batch_client: BatchAPIClient, sample_requests: list[BatchRequest]
    ) -> None:
        """Test creating batch JSONL file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "batch.jsonl"
            result_path = batch_client.create_batch_file(sample_requests, output_path)

            assert result_path == output_path
            assert output_path.exists()

            # Verify file content
            with open(output_path, encoding="utf-8") as f:
                lines = f.readlines()
                assert len(lines) == len(sample_requests)

                for i, line in enumerate(lines):
                    data = json.loads(line)
                    assert data["custom_id"] == sample_requests[i].custom_id

    def test_auto_generated_filename(
        self, batch_client: BatchAPIClient, sample_requests: list[BatchRequest]
    ) -> None:
        """Test auto-generated filename"""
        result_path = batch_client.create_batch_file(sample_requests)
        assert result_path.exists()
        assert result_path.name.startswith("batch_requests_")
        assert result_path.suffix == ".jsonl"

        # Cleanup
        result_path.unlink()

    def test_max_batch_size_validation(self, batch_client: BatchAPIClient) -> None:
        """Test batch size limit validation"""
        # Create requests exceeding limit
        large_batch = [
            BatchRequest(
                custom_id=f"req-{i}",
                url=BatchEndpoint.RESPONSES,
                body={"model": "gpt-4o-mini"},
            )
            for i in range(BatchAPIClient.MAX_BATCH_SIZE + 1)
        ]

        with pytest.raises(ValueError, match="exceeds maximum"):
            batch_client.create_batch_file(large_batch)


class TestBatchJobLifecycle:
    """Test batch job submission and lifecycle (integration test)"""

    @pytest.mark.slow
    def test_submit_and_track_batch(
        self, batch_client: BatchAPIClient, sample_requests: list[BatchRequest]
    ) -> None:
        """Test submitting batch job and tracking status"""
        # Note: This test submits a real batch job but doesn't wait for completion
        # (which takes ~24h). It only verifies submission and initial status.

        # Create and upload file
        file_path = batch_client.create_batch_file(sample_requests)
        file_id = batch_client.upload_batch_file(file_path)
        assert file_id.startswith("file-")

        # Create batch job
        batch = batch_client.create_batch(
            input_file_id=file_id,
            endpoint=BatchEndpoint.RESPONSES,
            metadata={"test": "integration"},
        )

        assert batch.id.startswith("batch_")
        assert batch.status in [BatchStatus.VALIDATING, BatchStatus.IN_PROGRESS]
        assert batch.endpoint == BatchEndpoint.RESPONSES
        assert batch.metadata.get("test") == "integration"

        # Check status
        status = batch_client.get_batch_status(batch.id)
        assert status.id == batch.id

        # Cancel the batch (cleanup)
        cancelled = batch_client.cancel_batch(batch.id)
        assert cancelled.status in [BatchStatus.CANCELLING, BatchStatus.CANCELLED]

        # Cleanup file
        file_path.unlink()

    def test_submit_with_chat_completions(
        self, batch_client: BatchAPIClient
    ) -> None:
        """Test submitting batch with chat completions endpoint"""
        requests = [
            BatchRequest(
                custom_id="chat-1",
                url=BatchEndpoint.CHAT_COMPLETIONS,
                body={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )
        ]

        file_path = batch_client.create_batch_file(requests)
        file_id = batch_client.upload_batch_file(file_path)

        batch = batch_client.create_batch(
            input_file_id=file_id,
            endpoint=BatchEndpoint.CHAT_COMPLETIONS,
        )

        assert batch.endpoint == BatchEndpoint.CHAT_COMPLETIONS

        # Cancel and cleanup
        batch_client.cancel_batch(batch.id)
        file_path.unlink()


class TestCostSavings:
    """Test batch API cost savings calculation"""

    def test_calculate_savings(self) -> None:
        """Test cost savings calculation"""
        pricing = {"prompt": 0.15, "completion": 0.60}  # gpt-4o-mini pricing
        prompt_tokens = 1000
        completion_tokens = 500

        savings = calculate_batch_savings(prompt_tokens, completion_tokens, pricing)

        # Verify calculations
        sync_cost = (1000 / 1_000_000) * 0.15 + (500 / 1_000_000) * 0.60
        batch_cost = sync_cost * 0.5

        assert abs(savings["sync_cost_usd"] - sync_cost) < 0.000001
        assert abs(savings["batch_cost_usd"] - batch_cost) < 0.000001
        assert abs(savings["savings_usd"] - (sync_cost - batch_cost)) < 0.000001
        assert savings["discount_pct"] == 50.0

    def test_large_volume_savings(self) -> None:
        """Test savings with large token volumes"""
        pricing = {"prompt": 2.5, "completion": 10.0}  # gpt-4o pricing
        prompt_tokens = 1_000_000  # 1M tokens
        completion_tokens = 500_000  # 500K tokens

        savings = calculate_batch_savings(prompt_tokens, completion_tokens, pricing)

        # With 1M prompt tokens at $2.5/M and 500K completion at $10/M:
        # Sync: 1*2.5 + 0.5*10 = $7.5
        # Batch: $7.5 * 0.5 = $3.75
        # Savings: $3.75

        assert abs(savings["sync_cost_usd"] - 7.5) < 0.01
        assert abs(savings["batch_cost_usd"] - 3.75) < 0.01
        assert abs(savings["savings_usd"] - 3.75) < 0.01


class TestBatchClientFactory:
    """Test batch client factory"""

    def test_create_client(self) -> None:
        """Test creating batch client"""
        client = create_batch_client()
        assert isinstance(client, BatchAPIClient)
        assert client.client is not None

    def test_create_with_custom_key(self) -> None:
        """Test creating with custom API key"""
        # This just tests instantiation, not actual API calls
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            client = create_batch_client(api_key=api_key)
            assert isinstance(client, BatchAPIClient)


class TestBatchConstants:
    """Test batch API constants and specifications"""

    def test_cost_multiplier(self) -> None:
        """Test that cost multiplier is 50% (0.5)"""
        assert BatchAPIClient.BATCH_COST_MULTIPLIER == 0.5

    def test_completion_window(self) -> None:
        """Test completion window is 24 hours"""
        assert BatchAPIClient.COMPLETION_WINDOW_HOURS == 24

    def test_max_batch_size(self) -> None:
        """Test maximum batch size"""
        assert BatchAPIClient.MAX_BATCH_SIZE == 50000
