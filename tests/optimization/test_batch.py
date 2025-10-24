"""
Tests for Batch Manager

Tests both /v1/messages and /v1/responses endpoints with mocked responses
and integration tests (skipped if no API key available).
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agdd.optimization.batch import (
    APIEndpoint,
    BatchManager,
    BatchRequestItem,
    BatchStatus,
    PriceCalculation,
    SLA,
)


class TestPriceCalculation:
    """Test price calculation with batch discount"""

    def test_50_percent_discount(self) -> None:
        """Test that batch discount is correctly applied at 50%"""
        original = 100.0
        calc = PriceCalculation.calculate(original)

        assert calc.original_price == 100.0
        assert calc.batch_discount_percent == 50.0
        assert calc.discounted_price == 50.0

    def test_various_prices(self) -> None:
        """Test discount calculation with various price points"""
        test_cases = [
            (0.0, 0.0),
            (10.0, 5.0),
            (99.99, 49.995),
            (1000.0, 500.0),
            (0.01, 0.005),
        ]

        for original, expected in test_cases:
            calc = PriceCalculation.calculate(original)
            assert calc.discounted_price == pytest.approx(expected)
            assert calc.batch_discount_percent == 50.0


class TestSLABasedBatching:
    """Test automatic batching based on SLA requirements"""

    def test_realtime_sla_no_batch(self) -> None:
        """Test that realtime SLA does not trigger batching"""
        assert BatchManager.should_batch(SLA.REALTIME) is False

    def test_standard_sla_batches(self) -> None:
        """Test that standard SLA triggers batching"""
        assert BatchManager.should_batch(SLA.STANDARD) is True

    def test_batch_sla_batches(self) -> None:
        """Test that batch SLA triggers batching"""
        assert BatchManager.should_batch(SLA.BATCH) is True


class TestBatchManagerInit:
    """Test BatchManager initialization"""

    def test_init_with_api_key(self) -> None:
        """Test initialization with explicit API key"""
        manager = BatchManager(api_key="test-key")
        assert manager.api_key == "test-key"
        assert manager.base_url == "https://api.anthropic.com"

    def test_init_from_env(self) -> None:
        """Test initialization from environment variable"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            manager = BatchManager()
            assert manager.api_key == "env-key"

    def test_init_without_key_raises(self) -> None:
        """Test that missing API key raises ValueError"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key required"):
                BatchManager()

    def test_custom_base_url(self) -> None:
        """Test initialization with custom base URL"""
        manager = BatchManager(api_key="test", base_url="https://custom.api.com/")
        assert manager.base_url == "https://custom.api.com"


@pytest.mark.asyncio
class TestBatchManagerMocked:
    """Test BatchManager with mocked HTTP responses"""

    async def test_create_batch_messages_endpoint(self) -> None:
        """Test batch creation for /v1/messages endpoint"""
        mock_response = {
            "id": "batch_123",
            "type": "message_batch",
            "processing_status": "in_progress",
            "request_counts": {"processing": 2},
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200, json=lambda: mock_response
            )

            async with BatchManager(api_key="test-key") as manager:
                requests = [
                    BatchRequestItem(
                        custom_id="req-1",
                        params={
                            "model": "claude-3-5-sonnet-20241022",
                            "max_tokens": 1024,
                            "messages": [{"role": "user", "content": "Hello"}],
                        },
                    ),
                    BatchRequestItem(
                        custom_id="req-2",
                        params={
                            "model": "claude-3-5-sonnet-20241022",
                            "max_tokens": 1024,
                            "messages": [{"role": "user", "content": "World"}],
                        },
                    ),
                ]

                result = await manager.create_batch(
                    requests, endpoint=APIEndpoint.MESSAGES
                )

                assert result.id == "batch_123"
                assert result.processing_status == BatchStatus.IN_PROGRESS
                assert result.request_counts == {"processing": 2}

    async def test_create_batch_responses_endpoint(self) -> None:
        """Test batch creation for /v1/responses endpoint"""
        mock_response = {
            "id": "batch_456",
            "type": "message_batch",
            "processing_status": "in_progress",
            "request_counts": {"processing": 1},
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200, json=lambda: mock_response
            )

            async with BatchManager(api_key="test-key") as manager:
                requests = [
                    BatchRequestItem(
                        custom_id="resp-1",
                        params={
                            "model": "claude-3-5-sonnet-20241022",
                            "max_tokens": 1024,
                            "prompt": "Explain quantum computing",
                        },
                    )
                ]

                result = await manager.create_batch(
                    requests, endpoint=APIEndpoint.RESPONSES
                )

                assert result.id == "batch_456"

                # Verify endpoint was set correctly in request
                call_args = mock_post.call_args
                payload = call_args.kwargs["json"]
                assert payload["requests"][0]["params"]["url"] == "/v1/responses"

    async def test_get_batch_status(self) -> None:
        """Test retrieving batch status"""
        mock_response = {
            "id": "batch_789",
            "type": "message_batch",
            "processing_status": "ended",
            "request_counts": {"succeeded": 5, "errored": 0},
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
            "ended_at": "2024-01-01T01:00:00Z",
            "results_url": "https://api.anthropic.com/results/batch_789",
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: mock_response
            )

            async with BatchManager(api_key="test-key") as manager:
                result = await manager.get_batch_status("batch_789")

                assert result.id == "batch_789"
                assert result.processing_status == BatchStatus.ENDED
                assert result.results_url == "https://api.anthropic.com/results/batch_789"
                assert result.ended_at is not None

    async def test_get_batch_results_success(self) -> None:
        """Test retrieving successful batch results"""
        status_response = {
            "id": "batch_complete",
            "type": "message_batch",
            "processing_status": "ended",
            "request_counts": {"succeeded": 2},
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
            "ended_at": "2024-01-01T01:00:00Z",
            "results_url": "https://api.anthropic.com/results/batch_complete",
        }

        results_response = """{"custom_id":"req-1","result":{"type":"message","content":[{"type":"text","text":"Response 1"}]}}
{"custom_id":"req-2","result":{"type":"message","content":[{"type":"text","text":"Response 2"}]}}"""

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:

            def get_side_effect(url: str) -> MagicMock:
                if "batches" in url:
                    return MagicMock(status_code=200, json=lambda: status_response)
                else:
                    return MagicMock(status_code=200, text=results_response)

            mock_get.side_effect = get_side_effect

            async with BatchManager(api_key="test-key") as manager:
                results = await manager.get_batch_results("batch_complete")

                assert len(results) == 2
                assert results[0].custom_id == "req-1"
                assert results[1].custom_id == "req-2"
                assert results[0].error is None
                assert results[1].error is None

    async def test_get_batch_results_not_complete_raises(self) -> None:
        """Test that getting results for incomplete batch raises error"""
        status_response = {
            "id": "batch_incomplete",
            "type": "message_batch",
            "processing_status": "in_progress",
            "request_counts": {"processing": 5},
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: status_response
            )

            async with BatchManager(api_key="test-key") as manager:
                with pytest.raises(RuntimeError, match="not complete"):
                    await manager.get_batch_results("batch_incomplete")

    async def test_wait_for_completion(self) -> None:
        """Test polling for batch completion"""
        responses = [
            {
                "id": "batch_wait",
                "type": "message_batch",
                "processing_status": "in_progress",
                "request_counts": {"processing": 3},
                "created_at": "2024-01-01T00:00:00Z",
                "expires_at": "2024-01-02T00:00:00Z",
            },
            {
                "id": "batch_wait",
                "type": "message_batch",
                "processing_status": "in_progress",
                "request_counts": {"processing": 3},
                "created_at": "2024-01-01T00:00:00Z",
                "expires_at": "2024-01-02T00:00:00Z",
            },
            {
                "id": "batch_wait",
                "type": "message_batch",
                "processing_status": "ended",
                "request_counts": {"succeeded": 3},
                "created_at": "2024-01-01T00:00:00Z",
                "expires_at": "2024-01-02T00:00:00Z",
                "ended_at": "2024-01-01T00:10:00Z",
            },
        ]

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                MagicMock(status_code=200, json=lambda r=r: r) for r in responses
            ]

            async with BatchManager(api_key="test-key") as manager:
                result = await manager.wait_for_completion(
                    "batch_wait", poll_interval=0.1, max_wait=timedelta(seconds=5)
                )

                assert result.processing_status == BatchStatus.ENDED
                assert mock_get.call_count == 3


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
)
class TestBatchManagerIntegration:
    """
    Integration tests with real Anthropic API

    These tests are skipped if ANTHROPIC_API_KEY environment variable is not set.
    """

    async def test_create_and_retrieve_batch(self) -> None:
        """Test creating a batch and retrieving its status"""
        async with BatchManager() as manager:
            requests = [
                BatchRequestItem(
                    custom_id=f"integration-test-{datetime.utcnow().timestamp()}",
                    params={
                        "model": "claude-3-5-sonnet-20241022",
                        "max_tokens": 100,
                        "messages": [
                            {"role": "user", "content": "Say 'integration test successful'"}
                        ],
                    },
                )
            ]

            # Create batch
            batch = await manager.create_batch(requests, endpoint=APIEndpoint.MESSAGES)
            assert batch.id
            assert batch.processing_status in (
                BatchStatus.IN_PROGRESS,
                BatchStatus.ENDED,
            )

            # Retrieve status
            status = await manager.get_batch_status(batch.id)
            assert status.id == batch.id

    async def test_batch_with_multiple_requests(self) -> None:
        """Test batch with multiple requests"""
        async with BatchManager() as manager:
            timestamp = datetime.utcnow().timestamp()
            requests = [
                BatchRequestItem(
                    custom_id=f"multi-test-{i}-{timestamp}",
                    params={
                        "model": "claude-3-5-sonnet-20241022",
                        "max_tokens": 50,
                        "messages": [{"role": "user", "content": f"Count to {i}"}],
                    },
                )
                for i in range(1, 4)
            ]

            batch = await manager.create_batch(requests)
            assert batch.id
            assert batch.request_counts.get("processing", 0) >= 3 or batch.request_counts.get(
                "succeeded", 0
            ) >= 3

    async def test_price_calculation_integration(self) -> None:
        """Test that price calculation works correctly (unit test, not API call)"""
        # This is more of a verification that our pricing model is correct
        # Actual API costs would need to be calculated from token usage

        # Simulate a request that would cost $1.00 normally
        normal_cost = 1.00
        calc = PriceCalculation.calculate(normal_cost)

        # Batch should be 50% cheaper
        assert calc.discounted_price == 0.50
        assert calc.batch_discount_percent == 50.0

        # Verify savings
        savings = normal_cost - calc.discounted_price
        assert savings == 0.50
