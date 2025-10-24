"""
A2A Agent Card - Agent metadata and capability descriptor.

An AgentCard is the primary means of describing an agent in the A2A network,
including its identity, capabilities, endpoints, and metadata. It serves as
a "business card" for agents to exchange during discovery and registration.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .types import AgentEndpoint, AgentIdentity, AgentMetadata, Capability


class AgentCard(BaseModel):
    """
    Agent Card - Complete agent descriptor.

    Combines identity, capabilities, endpoints, and metadata into a single
    transferable object for agent discovery and registration.
    """

    identity: AgentIdentity = Field(..., description="Agent identity information")
    capabilities: list[Capability] = Field(
        default_factory=list, description="List of capabilities/methods offered"
    )
    endpoints: list[AgentEndpoint] = Field(
        default_factory=list, description="Communication endpoints"
    )
    metadata: AgentMetadata | None = Field(None, description="Extended metadata")

    # Extension point: digital signature of the card content
    signature: str | None = Field(
        None,
        description="Digital signature of card content (for verification)",
    )

    def has_capability(self, capability_name: str) -> bool:
        """
        Check if agent has a specific capability.

        Args:
            capability_name: Name of the capability to check

        Returns:
            True if the agent has the capability, False otherwise
        """
        return any(cap.name == capability_name for cap in self.capabilities)

    def get_capability(self, capability_name: str) -> Capability | None:
        """
        Get capability by name.

        Args:
            capability_name: Name of the capability

        Returns:
            Capability object if found, None otherwise
        """
        for cap in self.capabilities:
            if cap.name == capability_name:
                return cap
        return None

    def get_endpoint(self, protocol: str) -> AgentEndpoint | None:
        """
        Get endpoint by protocol type.

        Args:
            protocol: Protocol type (e.g., "http", "amqp")

        Returns:
            First matching endpoint, or None if not found
        """
        for endpoint in self.endpoints:
            if endpoint.protocol == protocol:
                return endpoint
        return None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert agent card to dictionary.

        Returns:
            Dictionary representation of the agent card
        """
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentCard:
        """
        Create agent card from dictionary.

        Args:
            data: Dictionary containing agent card data

        Returns:
            AgentCard instance

        Raises:
            ValidationError: If data doesn't match schema
        """
        return cls.model_validate(data)

    def verify_signature(self, public_key: str | None = None) -> bool:
        """
        Verify digital signature of the agent card.

        This is a placeholder for future signature verification implementation.
        Currently always returns True (no verification).

        Args:
            public_key: Optional public key for verification (overrides card's key)

        Returns:
            True if signature is valid or not present, False if invalid
        """
        # TODO: Implement actual signature verification
        # This is a placeholder for future extension
        if self.signature is None:
            return True  # No signature to verify

        # Future implementation would:
        # 1. Extract card content (excluding signature field)
        # 2. Use public_key (or identity.public_key) to verify signature
        # 3. Return verification result

        return True

    def sign(self, private_key: str) -> None:
        """
        Sign the agent card with a private key.

        This is a placeholder for future signature implementation.
        Currently does nothing.

        Args:
            private_key: Private key for signing (PEM format)
        """
        # TODO: Implement actual signature generation
        # This is a placeholder for future extension

        # Future implementation would:
        # 1. Serialize card content (excluding signature field)
        # 2. Create signature using private_key
        # 3. Set self.signature to the generated signature

        pass


class AgentCardBuilder:
    """
    Builder for constructing AgentCard instances.

    Provides a fluent interface for building agent cards.
    """

    def __init__(self, agent_id: str, name: str, version: str):
        """
        Initialize builder with required identity fields.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable agent name
            version: Agent version
        """
        self._identity = AgentIdentity(agent_id=agent_id, name=name, version=version)
        self._capabilities: list[Capability] = []
        self._endpoints: list[AgentEndpoint] = []
        self._metadata: AgentMetadata | None = None
        self._signature: str | None = None

    def with_public_key(self, public_key: str) -> AgentCardBuilder:
        """Add public key to identity."""
        self._identity.public_key = public_key
        return self

    def add_capability(
        self,
        name: str,
        description: str | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> AgentCardBuilder:
        """Add a capability to the agent card."""
        capability = Capability(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
        )
        self._capabilities.append(capability)
        return self

    def add_endpoint(
        self,
        protocol: str,
        uri: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentCardBuilder:
        """Add an endpoint to the agent card."""
        endpoint = AgentEndpoint(protocol=protocol, uri=uri, metadata=metadata)
        self._endpoints.append(endpoint)
        return self

    def with_metadata(
        self,
        description: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        documentation_url: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> AgentCardBuilder:
        """Set metadata for the agent card."""
        self._metadata = AgentMetadata(
            description=description,
            owner=owner,
            tags=tags or [],
            documentation_url=documentation_url,
            created_at=created_at,
            updated_at=updated_at,
        )
        return self

    def with_signature(self, signature: str) -> AgentCardBuilder:
        """Set digital signature."""
        self._signature = signature
        return self

    def build(self) -> AgentCard:
        """
        Build the agent card.

        Returns:
            Constructed AgentCard instance
        """
        return AgentCard(
            identity=self._identity,
            capabilities=self._capabilities,
            endpoints=self._endpoints,
            metadata=self._metadata,
            signature=self._signature,
        )
