"""Tests for OfferOrchestratorMAG"""

from agdd.runners.agent_runner import AgentRunner


class TestOfferOrchestratorMAG:
    """Test suite for OfferOrchestratorMAG"""

    def test_basic_orchestration(self):
        """Test basic offer packet generation"""
        runner = AgentRunner()

        payload = {
            "role": "Software Engineer",
            "level": "Mid",
            "location": "Seattle, WA",
            "experience_years": 5,
        }

        output = runner.invoke_mag("offer-orchestrator-mag", payload)

        assert "offer" in output
        assert "metadata" in output
        assert output["metadata"]["generated_by"] == "OfferOrchestratorMAG"

    def test_metadata_presence(self):
        """Test that metadata is properly populated"""
        runner = AgentRunner()

        payload = {"role": "Engineer"}
        output = runner.invoke_mag("offer-orchestrator-mag", payload)

        metadata = output["metadata"]
        assert "generated_by" in metadata
        assert "run_id" in metadata
        assert "timestamp" in metadata
        assert "version" in metadata
        assert "task_count" in metadata
        assert "successful_tasks" in metadata

        # Verify values
        assert metadata["run_id"].startswith("mag-")
        assert metadata["version"] == "0.1.0"
        assert metadata["task_count"] >= 1
        assert metadata["successful_tasks"] >= 1

    def test_sag_delegation(self):
        """Test that MAG successfully delegates to SAG"""
        runner = AgentRunner()

        payload = {
            "role": "Senior Engineer",
            "level": "Senior",
            "location": "Remote",
            "experience_years": 8,
        }

        output = runner.invoke_mag("offer-orchestrator-mag", payload)

        # Verify delegation succeeded
        assert output["metadata"]["task_count"] == 1
        assert output["metadata"]["successful_tasks"] == 1

        # Verify offer content (came from SAG)
        offer = output["offer"]
        assert offer["role"] == "Senior Engineer"
        assert offer["base_salary"]["amount"] > 0

    def test_output_schema_compliance(self):
        """Test that output conforms to offer_packet schema"""
        runner = AgentRunner()

        payload = {"role": "Staff Engineer", "level": "Staff"}
        output = runner.invoke_mag("offer-orchestrator-mag", payload)

        # Required top-level fields
        assert "offer" in output
        # metadata is optional but we generate it
        assert "metadata" in output

        # offer structure (inherits from comp_advisor_output)
        offer = output["offer"]
        assert "role" in offer
        assert "base_salary" in offer
        assert "band" in offer

    def test_complex_candidate_profile(self):
        """Test with fully populated candidate profile"""
        runner = AgentRunner()

        payload = {
            "role": "Principal Engineer",
            "level": "Principal",
            "location": "New York, NY",
            "experience_years": 15,
            "notes": "Referral from CTO, exceptional systems design experience",
        }

        output = runner.invoke_mag("offer-orchestrator-mag", payload)

        assert output["metadata"]["successful_tasks"] == 1
        offer = output["offer"]

        # Principal should command high compensation
        assert offer["base_salary"]["amount"] >= 200000
        assert offer["sign_on_bonus"]["amount"] >= 50000

    def test_minimal_candidate_profile(self):
        """Test with minimal required fields"""
        runner = AgentRunner()

        payload = {"role": "Engineer"}  # Only required field

        output = runner.invoke_mag("offer-orchestrator-mag", payload)

        # Should still succeed
        assert output["metadata"]["successful_tasks"] == 1
        assert "offer" in output
        assert output["offer"]["role"] == "Engineer"
