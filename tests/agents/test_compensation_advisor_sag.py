"""Tests for CompensationAdvisorSAG

All tests in this module perform actual agent execution with LLM calls,
which can take 30-60+ seconds per test. Tests are marked as 'slow' to
allow quick CI runs with `-m "not slow"`.
"""

import pytest

from agdd.runners.agent_runner import AgentRunner, Delegation


@pytest.mark.slow
class TestCompensationAdvisorSAG:
    """Test suite for CompensationAdvisorSAG (actual agent execution)"""

    def test_basic_compensation_generation(self) -> None:
        """Test basic compensation offer generation"""
        runner = AgentRunner()

        delegation = Delegation(
            task_id="test-001",
            sag_id="compensation-advisor-sag",
            input={
                "candidate_profile": {
                    "role": "Software Engineer",
                    "level": "Mid",
                    "location": "Austin, TX",
                    "experience_years": 4,
                }
            },
            context={},
        )

        result = runner.invoke_sag(delegation)

        assert result.status == "success"
        assert "offer" in result.output

        offer = result.output["offer"]
        assert offer["role"] == "Software Engineer"
        assert "base_salary" in offer
        assert offer["base_salary"]["currency"] == "USD"
        assert offer["base_salary"]["amount"] > 0
        assert "band" in offer
        assert offer["band"]["min"] < offer["band"]["max"]

    def test_senior_level_compensation(self) -> None:
        """Test that senior roles get appropriate compensation"""
        runner = AgentRunner()

        delegation = Delegation(
            task_id="test-002",
            sag_id="compensation-advisor-sag",
            input={
                "candidate_profile": {
                    "role": "Senior Software Engineer",
                    "level": "Senior",
                    "location": "Remote",
                    "experience_years": 10,
                }
            },
            context={},
        )

        result = runner.invoke_sag(delegation)
        offer = result.output["offer"]

        # Senior should have higher sign-on bonus
        assert offer["sign_on_bonus"]["amount"] >= 20000
        # Base salary should be in senior range
        assert offer["base_salary"]["amount"] >= 150000

    def test_location_adjustment(self) -> None:
        """Test that location affects compensation"""
        runner = AgentRunner()

        # SF location
        delegation_sf = Delegation(
            task_id="test-003a",
            sag_id="compensation-advisor-sag",
            input={
                "candidate_profile": {
                    "role": "Engineer",
                    "level": "Mid",
                    "location": "San Francisco, CA",
                    "experience_years": 5,
                }
            },
            context={},
        )

        # Non-SF location
        delegation_other = Delegation(
            task_id="test-003b",
            sag_id="compensation-advisor-sag",
            input={
                "candidate_profile": {
                    "role": "Engineer",
                    "level": "Mid",
                    "location": "Remote",
                    "experience_years": 5,
                }
            },
            context={},
        )

        result_sf = runner.invoke_sag(delegation_sf)
        result_other = runner.invoke_sag(delegation_other)

        # SF should have higher salary due to location adjustment
        assert (
            result_sf.output["offer"]["base_salary"]["amount"]
            > result_other.output["offer"]["base_salary"]["amount"]
        )

    def test_experience_affects_salary(self) -> None:
        """Test that experience affects salary positioning in band"""
        runner = AgentRunner()

        # Junior (2 years)
        delegation_junior = Delegation(
            task_id="test-004a",
            sag_id="compensation-advisor-sag",
            input={
                "candidate_profile": {
                    "role": "Engineer",
                    "level": "Mid",
                    "location": "Remote",
                    "experience_years": 2,
                }
            },
            context={},
        )

        # Experienced (8 years)
        delegation_senior = Delegation(
            task_id="test-004b",
            sag_id="compensation-advisor-sag",
            input={
                "candidate_profile": {
                    "role": "Engineer",
                    "level": "Mid",
                    "location": "Remote",
                    "experience_years": 8,
                }
            },
            context={},
        )

        result_junior = runner.invoke_sag(delegation_junior)
        result_senior = runner.invoke_sag(delegation_senior)

        # More experience should yield higher salary
        assert (
            result_senior.output["offer"]["base_salary"]["amount"]
            > result_junior.output["offer"]["base_salary"]["amount"]
        )

    def test_output_schema_compliance(self) -> None:
        """Test that output conforms to comp_advisor_output schema"""
        runner = AgentRunner()

        delegation = Delegation(
            task_id="test-005",
            sag_id="compensation-advisor-sag",
            input={"candidate_profile": {"role": "PM", "level": "Senior"}},
            context={},
        )

        result = runner.invoke_sag(delegation)
        output = result.output

        # Required fields
        assert "offer" in output
        offer = output["offer"]
        assert "role" in offer
        assert "base_salary" in offer
        assert "band" in offer

        # base_salary structure
        assert "currency" in offer["base_salary"]
        assert "amount" in offer["base_salary"]

        # band structure
        assert "currency" in offer["band"]
        assert "min" in offer["band"]
        assert "max" in offer["band"]
