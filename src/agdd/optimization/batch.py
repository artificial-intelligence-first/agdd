"""
Batch Manager for Anthropic API

Supports both /v1/messages and /v1/responses endpoints with automatic batching
based on SLA requirements.
"""

import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field


class APIEndpoint(str, Enum):
    """Supported API endpoints for batching"""

    MESSAGES = "/v1/messages"
    RESPONSES = "/v1/responses"


class SLA(str, Enum):
    """Service Level Agreement types"""

    REALTIME = "realtime"
    STANDARD = "standard"
    BATCH = "batch"


class BatchStatus(str, Enum):
    """Batch processing status"""

    IN_PROGRESS = "in_progress"
    ENDED = "ended"
    CANCELING = "canceling"
    CANCELED = "canceled"


class BatchRequestItem(BaseModel):
    """Single request in a batch"""

    custom_id: str
    params: dict[str, Any]


class BatchRequest(BaseModel):
    """Batch request configuration"""

    requests: list[BatchRequestItem]


class BatchResponse(BaseModel):
    """Response from batch creation"""

    id: str
    type: Literal["message_batch"] = "message_batch"
    processing_status: BatchStatus
    request_counts: dict[str, int] = Field(default_factory=dict)
    ended_at: datetime | None = None
    created_at: datetime
    expires_at: datetime
    cancel_initiated_at: datetime | None = None
    results_url: str | None = None


class BatchResult(BaseModel):
    """Individual result from batch processing"""

    custom_id: str
    result: dict[str, Any]
    error: dict[str, Any] | None = None


class PriceCalculation(BaseModel):
    """Price calculation with batch discount"""

    original_price: float
    batch_discount_percent: float = 50.0
    discounted_price: float

    @classmethod
    def calculate(cls, original_price: float) -> "PriceCalculation":
        """Calculate price with 50% batch discount"""
        discount_percent = 50.0
        discounted = original_price * (1 - discount_percent / 100)
        return cls(
            original_price=original_price,
            batch_discount_percent=discount_percent,
            discounted_price=discounted,
        )


class BatchManager:
    """
    Manages batch requests to Anthropic API

    Supports both /v1/messages and /v1/responses endpoints with automatic
    batching based on SLA requirements.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com",
        timeout: float = 30.0,
    ):
        """
        Initialize BatchManager

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            base_url: Base URL for Anthropic API
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required: set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter"
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BatchManager":
        """Async context manager entry"""
        # api_key should never be None here due to __init__ validation
        assert self.api_key is not None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client (must be used within async context)"""
        if not self._client:
            raise RuntimeError("BatchManager must be used as async context manager")
        return self._client

    @staticmethod
    def should_batch(sla: SLA) -> bool:
        """
        Determine if request should be batched based on SLA

        Args:
            sla: Service level agreement type

        Returns:
            True if request should be batched, False otherwise
        """
        return sla != SLA.REALTIME

    async def create_batch(
        self,
        requests: list[BatchRequestItem],
        endpoint: APIEndpoint = APIEndpoint.MESSAGES,
    ) -> BatchResponse:
        """
        Create a new batch request

        Args:
            requests: List of requests to batch
            endpoint: API endpoint to use

        Returns:
            BatchResponse with batch ID and status

        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        payload = {
            "requests": [
                {
                    "custom_id": req.custom_id,
                    "params": {
                        **req.params,
                        # Ensure endpoint is set correctly
                        "url": endpoint.value,
                    },
                }
                for req in requests
            ]
        }

        response = await self.client.post("/v1/messages/batches", json=payload)
        response.raise_for_status()

        data = response.json()
        return BatchResponse(
            id=data["id"],
            processing_status=BatchStatus(data["processing_status"]),
            request_counts=data.get("request_counts", {}),
            created_at=datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            ),
            expires_at=datetime.fromisoformat(
                data["expires_at"].replace("Z", "+00:00")
            ),
            ended_at=(
                datetime.fromisoformat(data["ended_at"].replace("Z", "+00:00"))
                if data.get("ended_at")
                else None
            ),
            cancel_initiated_at=(
                datetime.fromisoformat(
                    data["cancel_initiated_at"].replace("Z", "+00:00")
                )
                if data.get("cancel_initiated_at")
                else None
            ),
            results_url=data.get("results_url"),
        )

    async def get_batch_status(self, batch_id: str) -> BatchResponse:
        """
        Get batch processing status

        Args:
            batch_id: ID of the batch to check

        Returns:
            BatchResponse with current status

        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        response = await self.client.get(f"/v1/messages/batches/{batch_id}")
        response.raise_for_status()

        data = response.json()
        return BatchResponse(
            id=data["id"],
            processing_status=BatchStatus(data["processing_status"]),
            request_counts=data.get("request_counts", {}),
            created_at=datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            ),
            expires_at=datetime.fromisoformat(
                data["expires_at"].replace("Z", "+00:00")
            ),
            ended_at=(
                datetime.fromisoformat(data["ended_at"].replace("Z", "+00:00"))
                if data.get("ended_at")
                else None
            ),
            cancel_initiated_at=(
                datetime.fromisoformat(
                    data["cancel_initiated_at"].replace("Z", "+00:00")
                )
                if data.get("cancel_initiated_at")
                else None
            ),
            results_url=data.get("results_url"),
        )

    async def get_batch_results(self, batch_id: str) -> list[BatchResult]:
        """
        Retrieve batch results

        Args:
            batch_id: ID of the batch to retrieve results for

        Returns:
            List of BatchResult objects

        Raises:
            httpx.HTTPStatusError: If API request fails
            RuntimeError: If batch is not complete
        """
        # First check if batch is complete
        status = await self.get_batch_status(batch_id)
        if status.processing_status != BatchStatus.ENDED:
            raise RuntimeError(
                f"Batch {batch_id} is not complete (status: {status.processing_status})"
            )

        if not status.results_url:
            raise RuntimeError(f"Batch {batch_id} has no results URL")

        # Fetch results from results URL
        response = await self.client.get(status.results_url)
        response.raise_for_status()

        # Results are returned as JSONL (one JSON object per line)
        import json

        results = []
        for line in response.text.strip().split("\n"):
            if line:
                data = json.loads(line)
                results.append(
                    BatchResult(
                        custom_id=data["custom_id"],
                        result=data.get("result", {}),
                        error=data.get("error"),
                    )
                )

        return results

    async def wait_for_completion(
        self,
        batch_id: str,
        poll_interval: float = 10.0,
        max_wait: timedelta = timedelta(hours=24),
    ) -> BatchResponse:
        """
        Poll batch status until completion

        Args:
            batch_id: ID of the batch to wait for
            poll_interval: Seconds between status checks
            max_wait: Maximum time to wait

        Returns:
            Final BatchResponse

        Raises:
            TimeoutError: If max_wait is exceeded
            httpx.HTTPStatusError: If API request fails
        """
        import asyncio
        from datetime import timezone

        start_time = datetime.now(timezone.utc)

        while True:
            status = await self.get_batch_status(batch_id)

            if status.processing_status in (BatchStatus.ENDED, BatchStatus.CANCELED):
                return status

            if datetime.now(timezone.utc) - start_time > max_wait:
                raise TimeoutError(
                    f"Batch {batch_id} did not complete within {max_wait}"
                )

            await asyncio.sleep(poll_interval)
