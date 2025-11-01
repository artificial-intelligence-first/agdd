"""Tests for cache key normalization utilities."""

from __future__ import annotations

from magsag.cache.key import compute_key, hash_stable, normalize_input


class TestNormalizeInput:
    """Test cases for normalize_input function."""

    def test_normalize_dict_keys(self) -> None:
        """Test that dictionary keys are sorted."""
        data = {"z": 1, "a": 2, "m": 3}
        result = normalize_input(data)
        assert list(result.keys()) == ["a", "m", "z"]

    def test_normalize_nested_dict(self) -> None:
        """Test that nested dictionaries are sorted recursively."""
        data = {"outer": {"z": 1, "a": 2}, "first": {"y": 3, "b": 4}}
        result = normalize_input(data)
        assert list(result.keys()) == ["first", "outer"]
        assert list(result["outer"].keys()) == ["a", "z"]
        assert list(result["first"].keys()) == ["b", "y"]

    def test_normalize_list_of_dicts(self) -> None:
        """Test that lists containing dictionaries are normalized."""
        data = [{"z": 1, "a": 2}, {"y": 3, "b": 4}]
        result = normalize_input(data)
        assert list(result[0].keys()) == ["a", "z"]
        assert list(result[1].keys()) == ["b", "y"]

    def test_normalize_preserves_values(self) -> None:
        """Test that normalization preserves all values."""
        data = {"b": [1, 2, 3], "a": {"nested": "value"}}
        result = normalize_input(data)
        assert result["a"]["nested"] == "value"
        assert result["b"] == [1, 2, 3]

    def test_normalize_empty_dict(self) -> None:
        """Test normalization of empty dictionary."""
        result = normalize_input({})
        assert result == {}

    def test_normalize_primitive_types(self) -> None:
        """Test that primitive types are returned as-is."""
        assert normalize_input("string") == "string"
        assert normalize_input(42) == 42
        assert normalize_input(3.14) == 3.14
        assert normalize_input(True) is True
        assert normalize_input(None) is None

    def test_normalize_list_order_independence(self) -> None:
        """Test that list item order doesn't affect normalized output."""
        data1 = {"items": [{"name": "z"}, {"name": "a"}, {"name": "m"}]}
        data2 = {"items": [{"name": "a"}, {"name": "m"}, {"name": "z"}]}
        result1 = normalize_input(data1)
        result2 = normalize_input(data2)
        assert result1 == result2
        # Verify items are sorted
        assert result1["items"][0] == {"name": "a"}
        assert result1["items"][1] == {"name": "m"}
        assert result1["items"][2] == {"name": "z"}

    def test_normalize_list_of_primitives_sorted(self) -> None:
        """Test that lists of primitives are sorted."""
        data1 = {"values": [3, 1, 2]}
        data2 = {"values": [1, 2, 3]}
        result1 = normalize_input(data1)
        result2 = normalize_input(data2)
        assert result1 == result2
        assert result1["values"] == [1, 2, 3]

    def test_normalize_list_of_strings_sorted(self) -> None:
        """Test that lists of strings are sorted."""
        data1 = {"tags": ["zebra", "apple", "mango"]}
        data2 = {"tags": ["apple", "mango", "zebra"]}
        result1 = normalize_input(data1)
        result2 = normalize_input(data2)
        assert result1 == result2
        assert result1["tags"] == ["apple", "mango", "zebra"]

    def test_normalize_nested_list_with_dicts(self) -> None:
        """Test that nested structures with lists of dicts are normalized."""
        data1 = {
            "outer": [
                {"inner": [{"z": 1}, {"a": 2}]},
                {"inner": [{"y": 3}, {"b": 4}]},
            ]
        }
        data2 = {
            "outer": [
                {"inner": [{"b": 4}, {"y": 3}]},
                {"inner": [{"a": 2}, {"z": 1}]},
            ]
        }
        result1 = normalize_input(data1)
        result2 = normalize_input(data2)
        assert result1 == result2


class TestHashStable:
    """Test cases for hash_stable function."""

    def test_hash_deterministic(self) -> None:
        """Test that hash is deterministic for same input."""
        data = {"tool": "test", "id": 1}
        hash1 = hash_stable(data)
        hash2 = hash_stable(data)
        assert hash1 == hash2

    def test_hash_order_independent(self) -> None:
        """Test that hash is same regardless of key order."""
        data1 = {"b": 2, "a": 1, "c": 3}
        data2 = {"a": 1, "b": 2, "c": 3}
        assert hash_stable(data1) == hash_stable(data2)

    def test_hash_different_data(self) -> None:
        """Test that different data produces different hashes."""
        data1 = {"tool": "test1"}
        data2 = {"tool": "test2"}
        assert hash_stable(data1) != hash_stable(data2)

    def test_hash_nested_order_independent(self) -> None:
        """Test that nested structures are order-independent."""
        data1 = {"outer": {"b": 2, "a": 1}}
        data2 = {"outer": {"a": 1, "b": 2}}
        assert hash_stable(data1) == hash_stable(data2)

    def test_hash_length(self) -> None:
        """Test that hash is SHA-256 length (64 hex chars)."""
        result = hash_stable({"test": "data"})
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_list(self) -> None:
        """Test hashing of list data."""
        data = [1, 2, 3]
        hash1 = hash_stable(data)
        hash2 = hash_stable(data)
        assert hash1 == hash2


class TestComputeKey:
    """Test cases for compute_key function."""

    def test_compute_key_deterministic(self) -> None:
        """Test that compute_key is deterministic."""
        key1 = compute_key(
            "template_v1",
            [{"name": "tool_a"}],
            {"type": "object"},
            {"streaming": True},
        )
        key2 = compute_key(
            "template_v1",
            [{"name": "tool_a"}],
            {"type": "object"},
            {"streaming": True},
        )
        assert key1 == key2

    def test_compute_key_tool_order_independent(self) -> None:
        """Test that tool spec order doesn't affect key."""
        key1 = compute_key(
            "template_v1",
            [{"name": "tool_a"}, {"name": "tool_b"}],
            {"type": "object"},
            {"streaming": True},
        )
        key2 = compute_key(
            "template_v1",
            [{"name": "tool_b"}, {"name": "tool_a"}],
            {"type": "object"},
            {"streaming": True},
        )
        assert key1 == key2

    def test_compute_key_dict_order_independent(self) -> None:
        """Test that dictionary key order doesn't affect key."""
        key1 = compute_key(
            "template_v1",
            [{"name": "tool_a", "id": 1}],
            {"type": "object", "name": "schema"},
            {"streaming": True, "async": False},
        )
        key2 = compute_key(
            "template_v1",
            [{"id": 1, "name": "tool_a"}],
            {"name": "schema", "type": "object"},
            {"async": False, "streaming": True},
        )
        assert key1 == key2

    def test_compute_key_different_templates(self) -> None:
        """Test that different templates produce different keys."""
        key1 = compute_key(
            "template_v1", [{"name": "tool_a"}], {}, {}
        )
        key2 = compute_key(
            "template_v2", [{"name": "tool_a"}], {}, {}
        )
        assert key1 != key2

    def test_compute_key_different_tools(self) -> None:
        """Test that different tool specs produce different keys."""
        key1 = compute_key(
            "template_v1", [{"name": "tool_a"}], {}, {}
        )
        key2 = compute_key(
            "template_v1", [{"name": "tool_b"}], {}, {}
        )
        assert key1 != key2

    def test_compute_key_empty_inputs(self) -> None:
        """Test compute_key with empty tool specs and configs."""
        key = compute_key("template_v1", [], {}, {})
        assert len(key) == 64  # SHA-256 hex length

    def test_compute_key_complex_nested_structure(self) -> None:
        """Test compute_key with complex nested structures."""
        tools = [
            {
                "name": "tool_a",
                "params": {"nested": {"deep": {"value": 1}}},
            },
            {
                "name": "tool_b",
                "params": {"list": [{"item": 1}, {"item": 2}]},
            },
        ]
        schema = {
            "properties": {
                "field1": {"type": "string"},
                "field2": {"type": "number"},
            }
        }
        caps = {"feature_flags": {"flag_a": True, "flag_b": False}}

        key1 = compute_key("template_v1", tools, schema, caps)
        key2 = compute_key("template_v1", tools, schema, caps)
        assert key1 == key2

    def test_compute_key_tools_without_name(self) -> None:
        """Test that tools without name are handled gracefully."""
        key = compute_key(
            "template_v1",
            [{"type": "function"}, {"name": "tool_a"}],
            {},
            {},
        )
        assert len(key) == 64

    def test_compute_key_schema_list_order_independent(self) -> None:
        """Test that list order in schema doesn't affect cache key."""
        schema1 = {
            "type": "object",
            "required": ["field_z", "field_a", "field_m"],
            "properties": ["prop_c", "prop_a", "prop_b"],
        }
        schema2 = {
            "type": "object",
            "required": ["field_a", "field_m", "field_z"],
            "properties": ["prop_a", "prop_b", "prop_c"],
        }
        key1 = compute_key("template_v1", [], schema1, {})
        key2 = compute_key("template_v1", [], schema2, {})
        assert key1 == key2

    def test_compute_key_capabilities_list_order_independent(self) -> None:
        """Test that list order in capabilities doesn't affect cache key."""
        caps1 = {
            "features": ["feature_z", "feature_a", "feature_m"],
            "models": [{"name": "model_b"}, {"name": "model_a"}],
        }
        caps2 = {
            "features": ["feature_a", "feature_m", "feature_z"],
            "models": [{"name": "model_a"}, {"name": "model_b"}],
        }
        key1 = compute_key("template_v1", [], {}, caps1)
        key2 = compute_key("template_v1", [], {}, caps2)
        assert key1 == key2

    def test_compute_key_all_components_list_order_independent(self) -> None:
        """Test comprehensive list order independence across all components."""
        # First set with one ordering
        key1 = compute_key(
            "template_v1",
            [{"name": "tool_z", "id": 3}, {"name": "tool_a", "id": 1}],
            {"required": ["z", "a"], "type": "object"},
            {"features": ["feat_c", "feat_a"]},
        )
        # Second set with different ordering but same content
        key2 = compute_key(
            "template_v1",
            [{"name": "tool_a", "id": 1}, {"name": "tool_z", "id": 3}],
            {"type": "object", "required": ["a", "z"]},
            {"features": ["feat_a", "feat_c"]},
        )
        assert key1 == key2
