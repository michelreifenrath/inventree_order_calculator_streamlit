import pytest
from src.order_calculation import calculate_required_parts # Import from src


class DummyAPI:
    pass  # Mock API object


@pytest.fixture
def dummy_api():
    return DummyAPI()


def test_calculate_required_parts_normal(dummy_api):
    result = calculate_required_parts(
        dummy_api,
        target_assemblies={1: 2},
    )
    assert isinstance(result, list)


def test_calculate_required_parts_edge_case(dummy_api):
    # Edge Case: Leere Assemblies
    result = calculate_required_parts(
        dummy_api,
        target_assemblies={},
    )
    assert result == []


def test_calculate_required_parts_failure(dummy_api):
    # Fehlerfall: API None
    result = calculate_required_parts(
        None,
        target_assemblies={1: 1},
    )
    assert result == []
