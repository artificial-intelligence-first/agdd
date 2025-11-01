"""
A2A Discovery Protocol - Agent discovery and registration.

Provides mechanisms for agents to discover each other in the network,
register their capabilities, and query for other agents by various criteria.
"""

from __future__ import annotations

from typing import Protocol

from .agent_card import AgentCard


class DiscoveryRegistry(Protocol):
    """
    Protocol for agent discovery registries.

    Defines the interface that any discovery backend must implement.
    This allows for pluggable backends (in-memory, Redis, etcd, etc.).
    """

    def register(self, card: AgentCard) -> None:
        """
        Register an agent in the discovery registry.

        Args:
            card: Agent card to register

        Raises:
            ValueError: If agent is already registered
        """
        ...

    def unregister(self, agent_id: str) -> None:
        """
        Unregister an agent from the discovery registry.

        Args:
            agent_id: Agent identifier to unregister
        """
        ...

    def find_by_id(self, agent_id: str) -> AgentCard | None:
        """
        Find agent by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent card if found, None otherwise
        """
        ...

    def find_by_capability(self, capability_name: str) -> list[AgentCard]:
        """
        Find agents by capability.

        Args:
            capability_name: Capability name to search for

        Returns:
            List of agent cards that offer the capability
        """
        ...

    def find_by_tags(self, tags: list[str]) -> list[AgentCard]:
        """
        Find agents by metadata tags.

        Args:
            tags: List of tags to match (OR logic)

        Returns:
            List of agent cards matching any of the tags
        """
        ...

    def list_all(self) -> list[AgentCard]:
        """
        List all registered agents.

        Returns:
            List of all registered agent cards
        """
        ...


class InMemoryDiscovery:
    """
    In-memory implementation of discovery registry.

    Suitable for development, testing, and single-process deployments.
    Not suitable for distributed systems (no persistence or sharing).
    """

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._agents: dict[str, AgentCard] = {}

    def register(self, card: AgentCard) -> None:
        """
        Register an agent in the discovery registry.

        Args:
            card: Agent card to register

        Raises:
            ValueError: If agent is already registered
        """
        agent_id = card.identity.agent_id
        if agent_id in self._agents:
            raise ValueError(f"Agent {agent_id} is already registered")
        self._agents[agent_id] = card

    def unregister(self, agent_id: str) -> None:
        """
        Unregister an agent from the discovery registry.

        Args:
            agent_id: Agent identifier to unregister
        """
        self._agents.pop(agent_id, None)

    def find_by_id(self, agent_id: str) -> AgentCard | None:
        """
        Find agent by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent card if found, None otherwise
        """
        return self._agents.get(agent_id)

    def find_by_capability(self, capability_name: str) -> list[AgentCard]:
        """
        Find agents by capability.

        Args:
            capability_name: Capability name to search for

        Returns:
            List of agent cards that offer the capability
        """
        return [card for card in self._agents.values() if card.has_capability(capability_name)]

    def find_by_tags(self, tags: list[str]) -> list[AgentCard]:
        """
        Find agents by metadata tags.

        Args:
            tags: List of tags to match (OR logic)

        Returns:
            List of agent cards matching any of the tags
        """
        if not tags:
            return []

        tag_set = set(tags)
        result: list[AgentCard] = []

        for card in self._agents.values():
            if card.metadata and card.metadata.tags:
                card_tags = set(card.metadata.tags)
                if card_tags & tag_set:  # Intersection (OR logic)
                    result.append(card)

        return result

    def list_all(self) -> list[AgentCard]:
        """
        List all registered agents.

        Returns:
            List of all registered agent cards
        """
        return list(self._agents.values())

    def clear(self) -> None:
        """Clear all registered agents (useful for testing)."""
        self._agents.clear()


class DiscoveryClient:
    """
    Client for interacting with agent discovery.

    Provides a high-level interface for agent discovery operations,
    wrapping the underlying registry backend.
    """

    def __init__(self, registry: DiscoveryRegistry | None = None):
        """
        Initialize discovery client.

        Args:
            registry: Discovery registry backend (defaults to InMemoryDiscovery)
        """
        self._registry = registry or InMemoryDiscovery()

    def register(self, card: AgentCard) -> None:
        """
        Register an agent.

        Args:
            card: Agent card to register

        Raises:
            ValueError: If agent is already registered
        """
        self._registry.register(card)

    def unregister(self, agent_id: str) -> None:
        """
        Unregister an agent.

        Args:
            agent_id: Agent identifier to unregister
        """
        self._registry.unregister(agent_id)

    def find_agent(self, agent_id: str) -> AgentCard | None:
        """
        Find an agent by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent card if found, None otherwise
        """
        return self._registry.find_by_id(agent_id)

    def find_agents_by_capability(self, capability_name: str) -> list[AgentCard]:
        """
        Find agents offering a specific capability.

        Args:
            capability_name: Capability name

        Returns:
            List of matching agent cards
        """
        return self._registry.find_by_capability(capability_name)

    def find_agents_by_tags(self, tags: list[str]) -> list[AgentCard]:
        """
        Find agents by tags.

        Args:
            tags: List of tags to match

        Returns:
            List of matching agent cards
        """
        return self._registry.find_by_tags(tags)

    def list_agents(self) -> list[AgentCard]:
        """
        List all registered agents.

        Returns:
            List of all agent cards
        """
        return self._registry.list_all()

    def query(
        self,
        capability: str | None = None,
        tags: list[str] | None = None,
    ) -> list[AgentCard]:
        """
        Query agents with multiple criteria.

        Results from different criteria are combined with AND logic.

        Args:
            capability: Optional capability name filter
            tags: Optional tag filters (OR logic within tags)

        Returns:
            List of agent cards matching all specified criteria
        """
        # Start with all agents
        results = self._registry.list_all()

        # Apply capability filter
        if capability is not None:
            capability_ids = {
                card.identity.agent_id for card in self._registry.find_by_capability(capability)
            }
            results = [card for card in results if card.identity.agent_id in capability_ids]

        # Apply tags filter
        if tags:
            tag_ids = {card.identity.agent_id for card in self._registry.find_by_tags(tags)}
            results = [card for card in results if card.identity.agent_id in tag_ids]

        return results
