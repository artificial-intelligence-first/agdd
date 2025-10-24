"""
OpenAI Batch API support for cost optimization.

Batch API provides:
- 50% cost reduction compared to synchronous API calls
- 24-hour completion time window
- Support for both /v1/chat/completions and /v1/responses endpoints

Reference: https://platform.openai.com/docs/guides/batch
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from openai import OpenAI


class BatchEndpoint(str, Enum):
    """Supported batch API endpoints"""

    CHAT_COMPLETIONS = "/v1/chat/completions"
    RESPONSES = "/v1/responses"


class BatchStatus(str, Enum):
    """Batch job status"""

    VALIDATING = "validating"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


@dataclass
class BatchRequest:
    """Single request in a batch"""

    custom_id: str
    method: Literal["POST"] = "POST"
    url: str = BatchEndpoint.RESPONSES
    body: Dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self) -> str:
        """Convert to JSONL format for batch API"""
        return json.dumps(
            {
                "custom_id": self.custom_id,
                "method": self.method,
                "url": self.url,
                "body": self.body,
            }
        )


@dataclass
class BatchResponse:
    """Single response from a batch"""

    custom_id: str
    response: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None


@dataclass
class BatchJob:
    """Batch job metadata"""

    id: str
    status: BatchStatus
    endpoint: str
    created_at: int
    completed_at: Optional[int] = None
    failed_at: Optional[int] = None
    expires_at: Optional[int] = None
    request_counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BatchAPIClient:
    """
    Client for OpenAI Batch API.

    Supports both chat.completions and responses endpoints with
    automatic cost tracking (50% discount applied).
    """

    # Batch API cost multiplier (50% discount)
    BATCH_COST_MULTIPLIER = 0.5

    # Maximum batch size and completion time
    MAX_BATCH_SIZE = 50000
    COMPLETION_WINDOW_HOURS = 24

    def __init__(self, client: Optional[OpenAI] = None, api_key: Optional[str] = None):
        """
        Initialize batch API client.

        Args:
            client: OpenAI client instance (created if not provided)
            api_key: API key (uses OPENAI_API_KEY env var if not provided)
        """
        if client:
            self.client = client
        else:
            self.client = OpenAI(api_key=api_key)

    def create_batch_file(
        self,
        requests: List[BatchRequest],
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Create JSONL file for batch processing.

        Args:
            requests: List of batch requests
            output_path: Output file path (auto-generated if not provided)

        Returns:
            Path to created JSONL file

        Raises:
            ValueError: If batch size exceeds maximum
        """
        if len(requests) > self.MAX_BATCH_SIZE:
            raise ValueError(
                f"Batch size {len(requests)} exceeds maximum {self.MAX_BATCH_SIZE}"
            )

        if output_path is None:
            timestamp = int(time.time())
            output_path = Path(f"batch_requests_{timestamp}.jsonl")

        with open(output_path, "w", encoding="utf-8") as f:
            for req in requests:
                f.write(req.to_jsonl() + "\n")

        return output_path

    def upload_batch_file(self, file_path: Path) -> str:
        """
        Upload batch file to OpenAI.

        Args:
            file_path: Path to JSONL batch file

        Returns:
            File ID for uploaded batch file
        """
        with open(file_path, "rb") as f:
            response = self.client.files.create(file=f, purpose="batch")
        return response.id

    def create_batch(
        self,
        input_file_id: str,
        endpoint: BatchEndpoint = BatchEndpoint.RESPONSES,
        completion_window: Literal["24h"] = "24h",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchJob:
        """
        Create batch processing job.

        Note: OpenAI Batch API uses a single /v1/batches endpoint for all batch
        operations. The 'endpoint' parameter specifies which API endpoint
        (/v1/responses or /v1/chat/completions) to use for processing the
        requests within the batch. This is different from some other batch APIs
        that use separate URLs for different endpoints.

        Args:
            input_file_id: ID of uploaded input file
            endpoint: API endpoint (/v1/responses or /v1/chat/completions)
            completion_window: Completion time window (currently only "24h")
            metadata: Optional metadata for tracking

        Returns:
            BatchJob with job metadata
        """
        batch_params: Dict[str, Any] = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": completion_window,
        }
        if metadata:
            batch_params["metadata"] = metadata

        response = self.client.batches.create(**batch_params)

        return BatchJob(
            id=response.id,
            status=BatchStatus(response.status),
            endpoint=response.endpoint,
            created_at=response.created_at,
            completed_at=response.completed_at,
            failed_at=response.failed_at,
            expires_at=response.expires_at,
            request_counts=(
                {
                    "total": response.request_counts.total,
                    "completed": response.request_counts.completed,
                    "failed": response.request_counts.failed,
                }
                if response.request_counts
                else {}
            ),
            metadata=response.metadata or {},
        )

    def get_batch_status(self, batch_id: str) -> BatchJob:
        """
        Get batch job status.

        Args:
            batch_id: Batch job ID

        Returns:
            BatchJob with current status
        """
        response = self.client.batches.retrieve(batch_id)

        return BatchJob(
            id=response.id,
            status=BatchStatus(response.status),
            endpoint=response.endpoint,
            created_at=response.created_at,
            completed_at=response.completed_at,
            failed_at=response.failed_at,
            expires_at=response.expires_at,
            request_counts=(
                {
                    "total": response.request_counts.total,
                    "completed": response.request_counts.completed,
                    "failed": response.request_counts.failed,
                }
                if response.request_counts
                else {}
            ),
            metadata=response.metadata or {},
        )

    def cancel_batch(self, batch_id: str) -> BatchJob:
        """
        Cancel a batch job.

        Args:
            batch_id: Batch job ID

        Returns:
            BatchJob with updated status
        """
        response = self.client.batches.cancel(batch_id)

        return BatchJob(
            id=response.id,
            status=BatchStatus(response.status),
            endpoint=response.endpoint,
            created_at=response.created_at,
            completed_at=response.completed_at,
            failed_at=response.failed_at,
            expires_at=response.expires_at,
            request_counts=(
                {
                    "total": response.request_counts.total,
                    "completed": response.request_counts.completed,
                    "failed": response.request_counts.failed,
                }
                if response.request_counts
                else {}
            ),
            metadata=response.metadata or {},
        )

    def download_results(
        self,
        batch_id: str,
        output_path: Optional[Path] = None,
    ) -> List[BatchResponse]:
        """
        Download batch results.

        Args:
            batch_id: Batch job ID
            output_path: Optional path to save raw results

        Returns:
            List of BatchResponse objects

        Raises:
            ValueError: If batch is not completed
        """
        batch = self.get_batch_status(batch_id)

        if batch.status != BatchStatus.COMPLETED:
            raise ValueError(f"Batch {batch_id} is not completed (status: {batch.status})")

        # Get batch details to retrieve output file ID
        batch_details = self.client.batches.retrieve(batch_id)
        if not batch_details.output_file_id:
            raise ValueError(f"Batch {batch_id} has no output file")

        # Download output file using streaming API
        file_response = self.client.files.content(batch_details.output_file_id)
        file_bytes = file_response.read()

        # Save to file if path provided
        if output_path:
            with open(output_path, "wb") as f:
                f.write(file_bytes)

        # Parse results from bytes
        file_text = file_bytes.decode("utf-8")
        results: List[BatchResponse] = []
        for line in file_text.strip().split("\n"):
            if not line:
                continue
            data = json.loads(line)
            results.append(
                BatchResponse(
                    custom_id=data["custom_id"],
                    response=data.get("response", {}),
                    error=data.get("error"),
                )
            )

        return results

    def wait_for_completion(
        self,
        batch_id: str,
        poll_interval: int = 60,
        timeout: Optional[int] = None,
    ) -> BatchJob:
        """
        Wait for batch completion with polling.

        Args:
            batch_id: Batch job ID
            poll_interval: Seconds between status checks
            timeout: Maximum wait time in seconds (None = no timeout)

        Returns:
            Completed BatchJob

        Raises:
            TimeoutError: If timeout is exceeded
            RuntimeError: If batch fails
        """
        start_time = time.time()

        while True:
            batch = self.get_batch_status(batch_id)

            if batch.status == BatchStatus.COMPLETED:
                return batch
            elif batch.status in [BatchStatus.FAILED, BatchStatus.EXPIRED, BatchStatus.CANCELLED]:
                raise RuntimeError(f"Batch {batch_id} ended with status: {batch.status}")

            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Batch {batch_id} did not complete within {timeout}s")

            time.sleep(poll_interval)

    def submit_batch(
        self,
        requests: List[BatchRequest],
        endpoint: BatchEndpoint = BatchEndpoint.RESPONSES,
        metadata: Optional[Dict[str, Any]] = None,
        wait: bool = False,
        poll_interval: int = 60,
    ) -> BatchJob:
        """
        High-level method to submit and optionally wait for batch.

        Args:
            requests: List of batch requests
            endpoint: API endpoint to use
            metadata: Optional metadata
            wait: If True, wait for completion
            poll_interval: Seconds between status checks if waiting

        Returns:
            BatchJob with status
        """
        # Create and upload file
        file_path = self.create_batch_file(requests)
        file_id = self.upload_batch_file(file_path)

        # Create batch job
        batch = self.create_batch(
            input_file_id=file_id,
            endpoint=endpoint,
            metadata=metadata,
        )

        # Optionally wait for completion
        if wait:
            batch = self.wait_for_completion(batch.id, poll_interval=poll_interval)

        return batch


def create_batch_client(api_key: Optional[str] = None) -> BatchAPIClient:
    """
    Factory function to create batch API client.

    Args:
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)

    Returns:
        BatchAPIClient instance
    """
    return BatchAPIClient(api_key=api_key)


def calculate_batch_savings(
    prompt_tokens: int,
    completion_tokens: int,
    model_pricing: Dict[str, float],
) -> Dict[str, float]:
    """
    Calculate cost savings from using batch API.

    Args:
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        model_pricing: Dict with 'prompt' and 'completion' prices per 1M tokens

    Returns:
        Dict with 'sync_cost', 'batch_cost', 'savings', 'discount_pct'
    """
    # Synchronous API cost
    sync_prompt_cost = (prompt_tokens / 1_000_000) * model_pricing["prompt"]
    sync_completion_cost = (completion_tokens / 1_000_000) * model_pricing["completion"]
    sync_cost = sync_prompt_cost + sync_completion_cost

    # Batch API cost (50% discount)
    batch_cost = sync_cost * BatchAPIClient.BATCH_COST_MULTIPLIER
    savings = sync_cost - batch_cost

    return {
        "sync_cost_usd": round(sync_cost, 6),
        "batch_cost_usd": round(batch_cost, 6),
        "savings_usd": round(savings, 6),
        "discount_pct": 50.0,
    }
