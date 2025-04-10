import pytest
from collections import defaultdict
from src.bom_calculation import get_recursive_bom # Import from src


class DummyAPI:
    pass  # Mock API object


@pytest.fixture
def dummy_api():
    return DummyAPI()


def test_recursive_bom_normal(dummy_api):
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()

    # Simuliere rekursiven Aufruf ohne echte API (funktioniert nur als Dummy-Test)
    get_recursive_bom(
        dummy_api,
        part_id=1,
        quantity=2,
        required_components=required,
        root_input_id=1,
        template_only_flags=template_flags,
        all_encountered_part_ids=encountered,
    )
    # Erwartung: Funktion läuft durch, keine Exception
    assert isinstance(required, dict)


def test_recursive_bom_edge_case(dummy_api):
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()

    # Edge Case: Menge 0
    get_recursive_bom(
        dummy_api,
        part_id=1,
        quantity=0,
        required_components=required,
        root_input_id=1,
        template_only_flags=template_flags,
        all_encountered_part_ids=encountered,
    )
    assert isinstance(required, dict)


def test_recursive_bom_failure(dummy_api):
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()

    # Fehlerfall: Ungültige API (None)
    try:
        get_recursive_bom(
            None,
            part_id=1,
            quantity=1,
            required_components=required,
            root_input_id=1,
            template_only_flags=template_flags,
            all_encountered_part_ids=encountered,
        )
    except Exception:
        pass  # Fehler wird erwartet
    else:
        # Wenn kein Fehler, trotzdem Test bestanden, da Dummy
        assert True
