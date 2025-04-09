# tests/test_inventree_logic.py
import pytest
from pytest_mock import MockerFixture
from collections import defaultdict
from inventree.api import (
    InvenTreeAPI,
)  # Import the real class for type hinting/isinstance checks if needed
from inventree.part import Part  # Import the real class

# Import functions to test
# Assuming inventree_logic.py is in the parent directory relative to tests/
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from inventree_logic import (
    connect_to_inventree,
    get_part_details,
    get_bom_items,
    get_recursive_bom,
    get_final_part_data,
    calculate_required_parts,
    get_parts_in_category, # Import the new function
)


# --- Fixtures ---
@pytest.fixture(autouse=True)
def clear_caches():
    """Fixture to automatically clear Streamlit caches before each test."""
    # Import cache functions here to avoid polluting global namespace if not needed elsewhere
    from inventree_logic import (
        get_part_details,
        get_bom_items,
        get_final_part_data,
        connect_to_inventree,
        get_parts_in_category, # Add to cache clearing
    )

    connect_to_inventree.clear()
    get_part_details.clear()
    get_bom_items.clear()
    get_final_part_data.clear()
    yield  # Run the test
    # Clear again after test if necessary, though usually clearing before is sufficient
    connect_to_inventree.clear()
    get_part_details.clear()
    get_bom_items.clear()
    get_final_part_data.clear()
    get_parts_in_category.clear() # Add to cache clearing


@pytest.fixture
def mock_api_class(mocker: MockerFixture):
    """Fixture for mocking the InvenTreeAPI class."""
    mock = mocker.patch("inventree_logic.InvenTreeAPI", autospec=True)
    # Configure the instance returned by the class constructor
    mock_instance = mock.return_value
    mock_instance.api_version = "0.13.0"  # Example version
    return mock


@pytest.fixture
def mock_part_class(mocker: MockerFixture):
    """Fixture for mocking the Part class."""
    mock = mocker.patch("inventree_logic.Part", autospec=True)
    return mock


# --- Helper to create mock Part instances ---
def create_mock_part(
    mocker: MockerFixture,
    pk: int,
    name: str,
    assembly: bool,
    in_stock: float | None,
    is_template: bool = False, # Add is_template
    variant_stock: float | None = 0.0, # Add variant_stock
):
    """Creates a mock Part object with specified attributes."""
    part_instance = mocker.MagicMock(spec=Part)
    part_instance.pk = pk
    part_instance.name = name
    part_instance.assembly = assembly
    # Simulate the _data attribute which seems to be used directly
    part_instance._data = {
        "in_stock": in_stock,
        "is_template": is_template,
        "variant_stock": variant_stock,
        "assembly": assembly, # Ensure assembly is also in _data if needed elsewhere
        "name": name, # Ensure name is also in _data if needed elsewhere
    }
    # Mock getBomItems if needed for specific tests
    part_instance.getBomItems = mocker.MagicMock(
        return_value=[]
    )  # Default to empty BOM
    return part_instance


# --- Test Functions ---


# Test connect_to_inventree
def test_connect_to_inventree_success(mocker: MockerFixture, mock_api_class):
    """Tests successful connection to InvenTree API."""
    url = "http://test.inventree.com"
    token = "test_token"

    api_instance = connect_to_inventree(url, token)

    mock_api_class.assert_called_once_with(url, token=token)
    assert api_instance is not None
    assert api_instance.api_version == "0.13.0"  # Check configured mock attribute


def test_connect_to_inventree_failure(mocker: MockerFixture, mock_api_class):
    """Tests handling of connection failure."""
    url = "http://test.inventree.com"
    token = "test_token"
    mock_api_class.side_effect = Exception(
        "Connection timed out"
    )  # Simulate constructor failure

    api_instance = connect_to_inventree(url, token)

    mock_api_class.assert_called_once_with(url, token=token)
    assert api_instance is None


# Test get_part_details
def test_get_part_details_success(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests successfully fetching part details."""
    mock_api_instance = (
        mock_api_class.return_value
    )  # Get the instance created by the fixture
    part_id = 101
    expected_details = {
        "assembly": False,
        "name": "Resistor 1k",
        "in_stock": 50.0,
        "is_template": False,
        "variant_stock": 0.0,
    }

    # Configure the mock Part instance returned by the mock Part class constructor
    mock_part_instance = create_mock_part(
        mocker,
        pk=part_id,
        name="Resistor 1k",
        assembly=False,
        in_stock=50.0,
        is_template=False,
        variant_stock=0.0,
    )
    mock_part_class.return_value = mock_part_instance

    details = get_part_details(mock_api_instance, part_id)

    mock_part_class.assert_called_once_with(mock_api_instance, pk=part_id)
    assert details == expected_details


def test_get_part_details_api_failure(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests handling failure during Part object instantiation."""
    mock_api_instance = mock_api_class.return_value
    part_id = 102
    mock_part_class.side_effect = Exception(
        "API Error"
    )  # Simulate Part() constructor failure

    details = get_part_details(mock_api_instance, part_id)

    mock_part_class.assert_called_once_with(mock_api_instance, pk=part_id)
    assert details is None


def test_get_part_details_part_not_found(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests handling case where Part object is created but has no pk (simulating not found)."""
    mock_api_instance = mock_api_class.return_value
    part_id = 103

    # Configure mock Part instance to simulate not found (e.g., pk is None or 0)
    mock_part_instance = mocker.MagicMock(spec=Part)
    mock_part_instance.pk = None  # Or 0, depending on library behavior
    mock_part_class.return_value = mock_part_instance

    details = get_part_details(mock_api_instance, part_id)

    mock_part_class.assert_called_once_with(mock_api_instance, pk=part_id)
    assert details is None


def test_get_part_details_invalid_api_object(mocker: MockerFixture):
    """Tests passing None as the API object."""
    details = get_part_details(None, 104)
    assert details is None


def test_get_part_details_handles_none_stock(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests fetching part details when in_stock is None."""
    mock_api_instance = mock_api_class.return_value
    part_id = 105
    expected_details = {
        "assembly": True,
        "name": "SubAssembly",
        "in_stock": 0.0, # Expect 0.0 for None stock
        "is_template": True, # Example: Make this a template
        "variant_stock": 15.0, # Example: Give it variant stock
    }

    # Configure the mock Part instance
    mock_part_instance = create_mock_part(
        mocker,
        pk=part_id,
        name="SubAssembly",
        assembly=True,
        in_stock=None, # Test None handling for in_stock
        is_template=True,
        variant_stock=15.0,
    )
    mock_part_class.return_value = mock_part_instance

    details = get_part_details(mock_api_instance, part_id)

    mock_part_class.assert_called_once_with(mock_api_instance, pk=part_id)
    assert details == expected_details


# --- Test get_bom_items ---


@pytest.fixture
def mock_get_part_details(mocker: MockerFixture):
    """Fixture to mock the get_part_details function within inventree_logic."""
    return mocker.patch("inventree_logic.get_part_details")


def test_get_bom_items_success(
    mocker: MockerFixture, mock_api_class, mock_part_class, mock_get_part_details
):
    """Tests successfully fetching BOM items for an assembly."""
    mock_api_instance = mock_api_class.return_value
    assembly_id = 201

    # Mock get_part_details to return assembly=True
    mock_get_part_details.return_value = {
        "assembly": True,
        "name": "Test Assembly",
        "in_stock": 1.0,
    }

    # Mock the Part instance and its getBomItems method
    mock_part_instance = create_mock_part(
        mocker, pk=assembly_id, name="Test Assembly", assembly=True, in_stock=1.0
    )
    mock_bom_item1 = mocker.MagicMock()
    mock_bom_item1.sub_part = 301  # Sub part ID
    mock_bom_item1.quantity = "2.0"  # API might return string
    mock_bom_item1.allow_variants = True # Example: Allow variants for this item
    mock_bom_item2 = mocker.MagicMock()
    mock_bom_item2.sub_part = 302
    mock_bom_item2.quantity = "1.5"
    mock_bom_item2.allow_variants = False # Example: Disallow variants for this item
    mock_part_instance.getBomItems.return_value = [mock_bom_item1, mock_bom_item2]
    mock_part_class.return_value = mock_part_instance

    expected_bom = [
        {"sub_part": 301, "quantity": 2.0, "allow_variants": True},
        {"sub_part": 302, "quantity": 1.5, "allow_variants": False},
    ]

    bom_items = get_bom_items(mock_api_instance, assembly_id)

    mock_get_part_details.assert_called_once_with(mock_api_instance, assembly_id)
    mock_part_class.assert_called_once_with(mock_api_instance, pk=assembly_id)
    mock_part_instance.getBomItems.assert_called_once()
    assert bom_items == expected_bom


def test_get_bom_items_not_assembly(
    mocker: MockerFixture, mock_api_class, mock_part_class, mock_get_part_details
):
    """Tests fetching BOM for a part that is not an assembly."""
    mock_api_instance = mock_api_class.return_value
    part_id = 202

    # Mock get_part_details to return assembly=False
    mock_get_part_details.return_value = {
        "assembly": False,
        "name": "Test Component",
        "in_stock": 10.0,
    }

    bom_items = get_bom_items(mock_api_instance, part_id)

    mock_get_part_details.assert_called_once_with(mock_api_instance, part_id)
    mock_part_class.assert_not_called()  # Should not try to fetch Part if not assembly
    assert bom_items == []  # Expect empty list for non-assemblies


def test_get_bom_items_empty_bom(
    mocker: MockerFixture, mock_api_class, mock_part_class, mock_get_part_details
):
    """Tests fetching BOM for an assembly with an empty BOM."""
    mock_api_instance = mock_api_class.return_value
    assembly_id = 203

    # Mock get_part_details to return assembly=True
    mock_get_part_details.return_value = {
        "assembly": True,
        "name": "Empty Assembly",
        "in_stock": 5.0,
    }

    # Mock the Part instance and its getBomItems method to return empty list
    mock_part_instance = create_mock_part(
        mocker, pk=assembly_id, name="Empty Assembly", assembly=True, in_stock=5.0
    )
    mock_part_instance.getBomItems.return_value = []  # Empty BOM
    mock_part_class.return_value = mock_part_instance

    bom_items = get_bom_items(mock_api_instance, assembly_id)

    mock_get_part_details.assert_called_once_with(mock_api_instance, assembly_id)
    mock_part_class.assert_called_once_with(mock_api_instance, pk=assembly_id)
    mock_part_instance.getBomItems.assert_called_once()
    assert bom_items == []  # Expect empty list


def test_get_bom_items_get_details_fails(
    mocker: MockerFixture, mock_api_class, mock_part_class, mock_get_part_details
):
    """Tests fetching BOM when the initial get_part_details call fails."""
    mock_api_instance = mock_api_class.return_value
    part_id = 204

    # Mock get_part_details to return None
    mock_get_part_details.return_value = None

    bom_items = get_bom_items(mock_api_instance, part_id)

    mock_get_part_details.assert_called_once_with(mock_api_instance, part_id)
    mock_part_class.assert_not_called()
    assert bom_items == []  # Expect empty list if details fail (as per current logic)


def test_get_bom_items_getbomitems_api_error(
    mocker: MockerFixture, mock_api_class, mock_part_class, mock_get_part_details
):
    """Tests handling an API error during the Part.getBomItems call."""
    mock_api_instance = mock_api_class.return_value
    assembly_id = 205

    # Mock get_part_details to return assembly=True
    mock_get_part_details.return_value = {
        "assembly": True,
        "name": "Error Assembly",
        "in_stock": 2.0,
    }

    # Mock the Part instance and make getBomItems raise an exception
    mock_part_instance = create_mock_part(
        mocker, pk=assembly_id, name="Error Assembly", assembly=True, in_stock=2.0
    )
    mock_part_instance.getBomItems.side_effect = Exception("API Timeout fetching BOM")
    mock_part_class.return_value = mock_part_instance

    bom_items = get_bom_items(mock_api_instance, assembly_id)

    mock_get_part_details.assert_called_once_with(mock_api_instance, assembly_id)
    mock_part_class.assert_called_once_with(mock_api_instance, pk=assembly_id)
    mock_part_instance.getBomItems.assert_called_once()
    assert bom_items is None  # Expect None on API error during fetch


def test_get_bom_items_invalid_api_object(mocker: MockerFixture):
    """Tests passing None as the API object."""
    bom_items = get_bom_items(None, 206)
    assert bom_items is None  # Expect None if API object is invalid

# --- Test get_parts_in_category ---

def test_get_parts_in_category_success(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests successfully fetching parts from a category."""
    mock_api_instance = mock_api_class.return_value
    category_id = 191
    expected_parts = [
        {"pk": 102, "name": "Apple"},
        {"pk": 101, "name": "Banana"}, # Intentionally out of order
        {"pk": 103, "name": "Cherry"},
    ]
    expected_sorted_parts = [ # Expected result should be sorted by name
        {"pk": 102, "name": "Apple"},
        {"pk": 101, "name": "Banana"},
        {"pk": 103, "name": "Cherry"},
    ]


    # Create mock Part objects
    mock_part_apple = create_mock_part(mocker, pk=102, name="Apple", assembly=False, in_stock=10)
    mock_part_banana = create_mock_part(mocker, pk=101, name="Banana", assembly=True, in_stock=5)
    mock_part_cherry = create_mock_part(mocker, pk=103, name="Cherry", assembly=False, in_stock=0)

    # Configure the 'list' method on the mocked Part class
    mock_part_class.list.return_value = [mock_part_apple, mock_part_banana, mock_part_cherry]

    parts = get_parts_in_category(mock_api_instance, category_id)

    # Check that the mocked Part.list was called correctly
    mock_part_class.list.assert_called_once_with(
        mock_api_instance, category=category_id, fields=["pk", "name"]
    )
    assert parts == expected_sorted_parts


def test_get_parts_in_category_empty(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests fetching parts from an empty category."""
    mock_api_instance = mock_api_class.return_value
    category_id = 192

    # Configure the 'list' method on the mocked Part class to return an empty list
    mock_part_class.list.return_value = []

    parts = get_parts_in_category(mock_api_instance, category_id)

    mock_part_class.list.assert_called_once_with(
        mock_api_instance, category=category_id, fields=["pk", "name"]
    )
    assert parts == []


def test_get_parts_in_category_api_error(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests handling an API error during Part.list call."""
    mock_api_instance = mock_api_class.return_value
    category_id = 193

    # Configure the 'list' method on the mocked Part class to raise an exception
    mock_part_class.list.side_effect = Exception("Network Error")

    parts = get_parts_in_category(mock_api_instance, category_id)

    mock_part_class.list.assert_called_once_with(
        mock_api_instance, category=category_id, fields=["pk", "name"]
    )
    assert parts is None


def test_get_parts_in_category_invalid_api_object(mocker: MockerFixture):
    """Tests passing None as the API object."""
    parts = get_parts_in_category(None, 194)
    assert parts is None


# --- Test get_recursive_bom ---


@pytest.fixture
def mock_get_bom_items(mocker: MockerFixture):
    """Fixture to mock the get_bom_items function within inventree_logic."""
    return mocker.patch("inventree_logic.get_bom_items")


@pytest.fixture
def mock_get_final_part_data(mocker: MockerFixture):
    """Fixture to mock the get_final_part_data function."""
    mock = mocker.patch("inventree_logic.get_final_part_data")
    # Default mock behavior - IMPORTANT: Update this default or override in tests
    # to include is_template and variant_stock
    def default_side_effect(api, part_ids_tuple):
        data = {}
        for pid in part_ids_tuple:
            # Provide some default structure, tests should override this
            data[pid] = {
                "name": f"Mock Part {pid}",
                "in_stock": 10.0,
                "is_template": False,
                "variant_stock": 0.0
            }
        return data
    mock.side_effect = default_side_effect
    return mock


@pytest.fixture
def mock_get_recursive_bom(mocker: MockerFixture):
    """Fixture to mock the get_recursive_bom function."""
    mock = mocker.patch("inventree_logic.get_recursive_bom")

    # Define a default side effect function that can be used or overridden
    # Now includes template_only_flags_dict
    def side_effect_func(api, part_id, quantity, required_components_dict, root_input_id, template_only_flags_dict):
        # Simulate adding components based on mocked data (simplified)
        # This mock needs to be adjusted per test case if template_only_flags logic is tested
        if part_id == 1: # Top Assembly
            required_components_dict[root_input_id][11] += quantity * 2.0 # Requires 2 of Base 1
            required_components_dict[root_input_id][12] += quantity * 1.0 # Requires 1 of Base 2
        elif part_id == 2: # Another Top Assembly
             required_components_dict[root_input_id][12] += quantity * 3.0 # Requires 3 of Base 2
        # Example: Simulate setting a flag if a specific template part is encountered
        # if part_id == some_template_id_used_in_test:
        #     template_only_flags_dict[some_base_component_id] = True
        pass # No return value needed as it modifies the dict in place

    mock.side_effect = side_effect_func # Set the default side effect
    return mock


# Helper function for configuring mock side effects based on part ID
def configure_mocks_for_recursion(
    mock_get_part_details, mock_get_bom_items, part_data_map, bom_data_map
):
    """Configures side effects for get_part_details and get_bom_items mocks."""

    def part_details_side_effect(api, part_id):
        return part_data_map.get(part_id)

    def bom_items_side_effect(api, part_id):
        return bom_data_map.get(part_id)

    mock_get_part_details.side_effect = part_details_side_effect
    mock_get_bom_items.side_effect = bom_items_side_effect


def test_get_recursive_bom_base_component(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """Tests recursion when the initial part is a base component."""
    mock_api_instance = mock_api_class.return_value
    base_part_id = 10
    initial_quantity = 5.0
    required_components = defaultdict(lambda: defaultdict(float))
    template_only_flags = defaultdict(bool) # Add the new dict
    root_id = 999 # Example root ID for this test

    part_data = {
        base_part_id: {"assembly": False, "name": "Base Part", "in_stock": 10.0}
    }
    bom_data = {}  # No BOMs needed

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    # Call already updated in previous attempt
    get_recursive_bom(
        mock_api_instance, base_part_id, initial_quantity, required_components, root_id, template_only_flags # Pass new dict
    )

    mock_get_part_details.assert_called_once_with(mock_api_instance, base_part_id)
    mock_get_bom_items.assert_not_called()  # Should not be called for base component
    # Assertion already updated in previous attempt
    assert required_components == {root_id: {base_part_id: initial_quantity}}
    assert template_only_flags == {} # Should be empty in this case


def test_get_recursive_bom_simple_assembly(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """Tests recursion for a single-level assembly."""
    mock_api_instance = mock_api_class.return_value
    assembly_id = 20
    base_part_id = 10
    initial_quantity = 2.0
    bom_qty = 3.0
    required_components = defaultdict(lambda: defaultdict(float))
    template_only_flags = defaultdict(bool) # Add the new dict
    root_id = assembly_id # Use assembly ID as root ID for this test

    part_data = {
        assembly_id: {"assembly": True, "name": "Simple Assembly", "in_stock": 1.0},
        base_part_id: {"assembly": False, "name": "Base Part", "in_stock": 10.0},
    }
    bom_data = {assembly_id: [{"sub_part": base_part_id, "quantity": bom_qty}]}

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    # Call already updated
    get_recursive_bom(
        mock_api_instance, assembly_id, initial_quantity, required_components, root_id, template_only_flags # Pass new dict
    )

    assert mock_get_part_details.call_count == 2
    mock_get_part_details.assert_any_call(mock_api_instance, assembly_id)
    mock_get_part_details.assert_any_call(mock_api_instance, base_part_id)
    mock_get_bom_items.assert_called_once_with(mock_api_instance, assembly_id)
    assert required_components == {
        base_part_id: initial_quantity * bom_qty
    }  # 2.0 * 3.0 = 6.0


def test_get_recursive_bom_multi_level(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """Tests recursion for a multi-level assembly."""
    mock_api_instance = mock_api_class.return_value
    top_assembly_id = 30
    sub_assembly_id = 40
    base_part_id = 10
    initial_quantity = 2.0
    bom_qty1 = 3.0  # Top -> Sub
    bom_qty2 = 4.0  # Sub -> Base
    # required_components already updated
    root_id = top_assembly_id # Use top assembly ID as root ID

    part_data = {
        top_assembly_id: {"assembly": True, "name": "Top Assembly", "in_stock": 1.0},
        sub_assembly_id: {"assembly": True, "name": "Sub Assembly", "in_stock": 5.0},
        base_part_id: {"assembly": False, "name": "Base Part", "in_stock": 10.0},
    }
    bom_data = {
        top_assembly_id: [{"sub_part": sub_assembly_id, "quantity": bom_qty1}],
        sub_assembly_id: [{"sub_part": base_part_id, "quantity": bom_qty2}],
    }

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    # Call already updated
    get_recursive_bom(
        mock_api_instance, top_assembly_id, initial_quantity, required_components, root_id, template_only_flags # Pass new dict
    )

    assert mock_get_part_details.call_count == 3
    mock_get_part_details.assert_any_call(mock_api_instance, top_assembly_id)
    mock_get_part_details.assert_any_call(mock_api_instance, sub_assembly_id)
    mock_get_part_details.assert_any_call(mock_api_instance, base_part_id)
    assert mock_get_bom_items.call_count == 2
    mock_get_bom_items.assert_any_call(mock_api_instance, top_assembly_id)
    mock_get_bom_items.assert_any_call(mock_api_instance, sub_assembly_id)
    assert required_components == {
        base_part_id: initial_quantity * bom_qty1 * bom_qty2
    }  # 2.0 * 3.0 * 4.0 = 24.0


def test_get_recursive_bom_multiple_base_components(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """Tests recursion for an assembly with multiple different base components."""
    mock_api_instance = mock_api_class.return_value
    assembly_id = 50
    base1_id = 11
    base2_id = 12
    initial_quantity = 1.0
    bom_qty1 = 2.0
    bom_qty2 = 3.0
    # required_components already updated
    root_id = assembly_id # Use assembly ID as root ID

    part_data = {
        assembly_id: {"assembly": True, "name": "Multi Base Assembly", "in_stock": 1.0},
        base1_id: {"assembly": False, "name": "Base Part 1", "in_stock": 10.0},
        base2_id: {"assembly": False, "name": "Base Part 2", "in_stock": 20.0},
    }
    bom_data = {
        assembly_id: [
            {"sub_part": base1_id, "quantity": bom_qty1},
            {"sub_part": base2_id, "quantity": bom_qty2},
        ]
    }

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    # Call already updated
    get_recursive_bom(
        mock_api_instance, assembly_id, initial_quantity, required_components, root_id, template_only_flags # Pass new dict
    )

    assert mock_get_part_details.call_count == 3
    assert mock_get_bom_items.call_count == 1
    assert required_components == {
        base1_id: initial_quantity * bom_qty1,  # 1.0 * 2.0 = 2.0
        base2_id: initial_quantity * bom_qty2,  # 1.0 * 3.0 = 3.0
    }


def test_get_recursive_bom_shared_component(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """Tests recursion where a base component is used in multiple sub-assemblies."""
    mock_api_instance = mock_api_class.return_value
    top_id = 60
    sub1_id = 71
    sub2_id = 72
    base_id = 15  # Shared base component
    initial_quantity = 1.0
    bom_qty_top_sub1 = 2.0
    bom_qty_top_sub2 = 3.0
    bom_qty_sub1_base = 4.0
    bom_qty_sub2_base = 5.0
    # required_components already updated
    root_id = top_assembly_id # Use top assembly ID as root ID

    part_data = {
        top_id: {"assembly": True, "name": "Top Shared", "in_stock": 1.0},
        sub1_id: {"assembly": True, "name": "Sub 1", "in_stock": 1.0},
        sub2_id: {"assembly": True, "name": "Sub 2", "in_stock": 1.0},
        base_id: {"assembly": False, "name": "Shared Base", "in_stock": 100.0},
    }
    bom_data = {
        top_id: [
            {"sub_part": sub1_id, "quantity": bom_qty_top_sub1},
            {"sub_part": sub2_id, "quantity": bom_qty_top_sub2},
        ],
        sub1_id: [{"sub_part": base_id, "quantity": bom_qty_sub1_base}],
        sub2_id: [{"sub_part": base_id, "quantity": bom_qty_sub2_base}],
    }

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    get_recursive_bom(mock_api_instance, top_id, initial_quantity, required_components)

    assert mock_get_part_details.call_count == 5  # Top, Sub1, Sub2, Base (called twice)
    assert mock_get_bom_items.call_count == 3  # Top, Sub1, Sub2
    expected_qty = (initial_quantity * bom_qty_top_sub1 * bom_qty_sub1_base) + (
        initial_quantity * bom_qty_top_sub2 * bom_qty_sub2_base
    )
    # (1.0 * 2.0 * 4.0) + (1.0 * 3.0 * 5.0) = 8.0 + 15.0 = 23.0
    assert required_components == {base_id: expected_qty}


def test_get_recursive_bom_part_details_fail_mid_recursion(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """Tests recursion stops for a branch if get_part_details fails."""
    mock_api_instance = mock_api_class.return_value
    top_id = 80
    sub_ok_id = 81
    sub_fail_id = 82  # This part's details will fail
    base_ok_id = 16
    base_fail_id = 17  # Should not be reached
    initial_quantity = 1.0
    # required_components already updated
    root_id = top_assembly_id # Use top assembly ID as root ID

    part_data = {
        top_id: {"assembly": True, "name": "Top Fail Mid", "in_stock": 1.0},
        sub_ok_id: {"assembly": True, "name": "Sub OK", "in_stock": 1.0},
        sub_fail_id: None,  # Simulate failure for this ID
        base_ok_id: {"assembly": False, "name": "Base OK", "in_stock": 10.0},
        # base_fail_id details are not needed as recursion should stop
    }
    bom_data = {
        top_id: [
            {"sub_part": sub_ok_id, "quantity": 2.0},
            {"sub_part": sub_fail_id, "quantity": 3.0},
        ],
        sub_ok_id: [{"sub_part": base_ok_id, "quantity": 4.0}],
        sub_fail_id: [
            {"sub_part": base_fail_id, "quantity": 5.0}
        ],  # This BOM won't be fetched
    }

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    get_recursive_bom(mock_api_instance, top_id, initial_quantity, required_components)

    # Called for Top, Sub OK, Sub Fail, Base OK
    assert mock_get_part_details.call_count == 4
    mock_get_part_details.assert_any_call(mock_api_instance, top_id)
    mock_get_part_details.assert_any_call(mock_api_instance, sub_ok_id)
    mock_get_part_details.assert_any_call(
        mock_api_instance, sub_fail_id
    )  # Called, but returns None
    mock_get_part_details.assert_any_call(mock_api_instance, base_ok_id)

    # Called for Top, Sub OK. Not called for Sub Fail because details failed.
    assert mock_get_bom_items.call_count == 2
    mock_get_bom_items.assert_any_call(mock_api_instance, top_id)
    mock_get_bom_items.assert_any_call(mock_api_instance, sub_ok_id)

    # Only the base component from the successful branch should be included
    assert required_components == {base_ok_id: 1.0 * 2.0 * 4.0}  # 8.0


def test_get_recursive_bom_bom_items_fail_mid_recursion(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """Tests recursion stops for a branch if get_bom_items fails."""
    mock_api_instance = mock_api_class.return_value
    top_id = 90
    sub_ok_id = 91
    sub_fail_id = 92  # This part's BOM fetch will fail
    base_ok_id = 18
    base_fail_id = 19  # Should not be reached
    initial_quantity = 1.0
    required_components = defaultdict(lambda: defaultdict(float))
    template_only_flags = defaultdict(bool) # Add the new dict
    root_id = top_id # Use top assembly ID as root ID

    part_data = {
        top_id: {"assembly": True, "name": "Top BOM Fail Mid", "in_stock": 1.0},
        sub_ok_id: {"assembly": True, "name": "Sub OK", "in_stock": 1.0},
        sub_fail_id: {"assembly": True, "name": "Sub BOM Fail", "in_stock": 1.0},
        base_ok_id: {"assembly": False, "name": "Base OK", "in_stock": 10.0},
        base_fail_id: {"assembly": False, "name": "Base Fail", "in_stock": 10.0},
    }
    bom_data = {
        top_id: [
            {"sub_part": sub_ok_id, "quantity": 2.0},
            {"sub_part": sub_fail_id, "quantity": 3.0},
        ],
        sub_ok_id: [{"sub_part": base_ok_id, "quantity": 4.0}],
        sub_fail_id: None,  # Simulate failure for this BOM fetch
    }

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    get_recursive_bom(mock_api_instance, top_id, initial_quantity, required_components, root_id, template_only_flags) # Pass new dict

    # Called for Top, Sub OK, Sub Fail, Base OK. Base Fail is NOT called as BOM fetch for Sub Fail returns None.
    assert mock_get_part_details.call_count == 4
    mock_get_part_details.assert_any_call(mock_api_instance, top_id)
    mock_get_part_details.assert_any_call(mock_api_instance, sub_ok_id)
    mock_get_part_details.assert_any_call(mock_api_instance, sub_fail_id)
    mock_get_part_details.assert_any_call(mock_api_instance, base_ok_id)
    # Note: Base Fail details might be called depending on exact execution order within the loop,
    # but its quantity won't be added. Let's assume it might be called.
    # mock_get_part_details.assert_any_call(mock_api_instance, base_fail_id) # This might or might not happen

    # Called for Top, Sub OK, Sub Fail (returns None)
    assert mock_get_bom_items.call_count == 3
    mock_get_bom_items.assert_any_call(mock_api_instance, top_id)
    mock_get_bom_items.assert_any_call(mock_api_instance, sub_ok_id)
    mock_get_bom_items.assert_any_call(
        mock_api_instance, sub_fail_id
    )  # Called, but returns None

    # Only the base component from the successful branch should be included
    assert required_components == {root_id: {base_ok_id: 1.0 * 2.0 * 4.0}}  # 8.0
# --- Tests for Variant Logic ---

def test_get_recursive_bom_template_variants_disallowed(
    mock_api_class, mock_get_part_details, mock_get_bom_items
):
    """
    Tests that template_only_flags is set correctly when a BOM item
    uses a template part but has allow_variants=False.
    """
    mock_api_instance = mock_api_class.return_value
    top_assembly_id = 1000
    template_part_id = 1001
    initial_quantity = 5.0
    bom_qty = 2.0
    required_components = defaultdict(lambda: defaultdict(float))
    template_only_flags = defaultdict(bool)
    root_id = top_assembly_id

    part_data = {
        top_assembly_id: {"assembly": True, "name": "Top Assembly", "in_stock": 1.0, "is_template": False, "variant_stock": 0.0},
        template_part_id: {"assembly": False, "name": "Template Part", "in_stock": 10.0, "is_template": True, "variant_stock": 5.0}, # Is a template, but not assembly
    }
    # Mock BOM item for the template part with allow_variants=False
    bom_data = {
        top_assembly_id: [
            {"sub_part": template_part_id, "quantity": bom_qty, "allow_variants": False}
        ]
    }

    configure_mocks_for_recursion(
        mock_get_part_details, mock_get_bom_items, part_data, bom_data
    )

    get_recursive_bom(
        mock_api_instance, top_assembly_id, initial_quantity, required_components, root_id, template_only_flags
    )

    # Assertions
    mock_get_part_details.assert_any_call(mock_api_instance, top_assembly_id)
    mock_get_part_details.assert_any_call(mock_api_instance, template_part_id)
    mock_get_bom_items.assert_called_once_with(mock_api_instance, top_assembly_id)

    # The template part itself should be added as a requirement
    expected_qty = initial_quantity * bom_qty
    assert required_components == {root_id: {template_part_id: expected_qty}}

    # Crucially, the template_only_flags should be set for the template part ID
    assert template_only_flags == {template_part_id: True}


    assert template_only_flags == {} # Should be empty


# --- Test get_final_part_data ---


def test_get_final_part_data_success(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests successfully fetching final data for multiple parts."""
    mock_api_instance = mock_api_class.return_value
    part_ids_tuple = (11, 12)
    part_ids_list = list(part_ids_tuple)

    # Mock parts returned by Part.list
    mock_part1 = create_mock_part(
        mocker, pk=11, name="Base Part 1", assembly=False, in_stock=10.0
    )
    mock_part2 = create_mock_part(
        mocker, pk=12, name="Base Part 2", assembly=False, in_stock=20.5
    )
    mock_part_class.list.return_value = [mock_part1, mock_part2]

    expected_data = {
        11: {"name": "Base Part 1", "in_stock": 10.0},
        12: {"name": "Base Part 2", "in_stock": 20.5},
    }

    final_data = get_final_part_data(mock_api_instance, part_ids_tuple)

    mock_part_class.list.assert_called_once_with(
        mock_api_instance, pk__in=part_ids_list
    )
    assert final_data == expected_data


def test_get_final_part_data_empty_input(mock_api_class, mock_part_class):
    """Tests handling of an empty tuple of part IDs."""
    mock_api_instance = mock_api_class.return_value
    part_ids_tuple = ()

    final_data = get_final_part_data(mock_api_instance, part_ids_tuple)

    mock_part_class.list.assert_not_called()
    assert final_data == {}


def test_get_final_part_data_missed_ids(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests handling when Part.list returns fewer items than requested."""
    mock_api_instance = mock_api_class.return_value
    part_ids_tuple = (11, 12, 13)  # Request 3 parts
    part_ids_list = list(part_ids_tuple)

    # Mock Part.list returning only one part
    mock_part1 = create_mock_part(
        mocker, pk=11, name="Base Part 1", assembly=False, in_stock=10.0
    )
    mock_part_class.list.return_value = [mock_part1]

    expected_data = {
        11: {"name": "Base Part 1", "in_stock": 10.0},
        12: {"name": "Unknown (ID: 12)", "in_stock": 0.0},  # Fallback for missing
        13: {"name": "Unknown (ID: 13)", "in_stock": 0.0},  # Fallback for missing
    }

    final_data = get_final_part_data(mock_api_instance, part_ids_tuple)

    mock_part_class.list.assert_called_once_with(
        mock_api_instance, pk__in=part_ids_list
    )
    assert final_data == expected_data


def test_get_final_part_data_api_returns_empty(mock_api_class, mock_part_class):
    """Tests handling when Part.list returns an empty list."""
    mock_api_instance = mock_api_class.return_value
    part_ids_tuple = (11, 12)
    part_ids_list = list(part_ids_tuple)

    # Mock Part.list returning empty list
    mock_part_class.list.return_value = []

    expected_data = {
        11: {"name": "Unknown (ID: 11)", "in_stock": 0.0},  # Fallback
        12: {"name": "Unknown (ID: 12)", "in_stock": 0.0},  # Fallback
    }

    final_data = get_final_part_data(mock_api_instance, part_ids_tuple)

    mock_part_class.list.assert_called_once_with(
        mock_api_instance, pk__in=part_ids_list
    )
    assert final_data == expected_data


def test_get_final_part_data_api_error(mock_api_class, mock_part_class):
    """Tests handling when Part.list raises an exception."""
    mock_api_instance = mock_api_class.return_value
    part_ids_tuple = (11, 12)
    part_ids_list = list(part_ids_tuple)

    # Mock Part.list raising an exception
    mock_part_class.list.side_effect = Exception("Database connection failed")

    expected_data = {
        11: {"name": "Unknown (ID: 11)", "in_stock": 0.0},  # Fallback on error
        12: {"name": "Unknown (ID: 12)", "in_stock": 0.0},  # Fallback on error
    }

    final_data = get_final_part_data(mock_api_instance, part_ids_tuple)

    mock_part_class.list.assert_called_once_with(
        mock_api_instance, pk__in=part_ids_list
    )
    assert final_data == expected_data


def test_get_final_part_data_invalid_api_object(mock_part_class):
    """Tests passing None as the API object."""
    part_ids_tuple = (11, 12)
    expected_data = {
        11: {"name": "Unknown (ID: 11)", "in_stock": 0.0},  # Fallback
        12: {"name": "Unknown (ID: 12)", "in_stock": 0.0},  # Fallback
    }
    final_data = get_final_part_data(None, part_ids_tuple)
    mock_part_class.list.assert_not_called()
    assert final_data == expected_data


def test_get_final_part_data_handles_none_stock(
    mocker: MockerFixture, mock_api_class, mock_part_class
):
    """Tests handling parts with None stock value during final data fetch."""
    mock_api_instance = mock_api_class.return_value
    part_ids_tuple = (11, 12)
    part_ids_list = list(part_ids_tuple)

    # Mock parts returned by Part.list
    mock_part1 = create_mock_part(
        mocker, pk=11, name="Base Part 1", assembly=False, in_stock=10.0
    )
    mock_part2 = create_mock_part(
        mocker, pk=12, name="Base Part None Stock", assembly=False, in_stock=None
    )  # Stock is None
    mock_part_class.list.return_value = [mock_part1, mock_part2]

    expected_data = {
        11: {"name": "Base Part 1", "in_stock": 10.0},
        12: {
            "name": "Base Part None Stock",
            "in_stock": 0.0,
        },  # Expect 0.0 for None stock
    }

    final_data = get_final_part_data(mock_api_instance, part_ids_tuple)

    mock_part_class.list.assert_called_once_with(
        mock_api_instance, pk__in=part_ids_list
    )
    assert final_data == expected_data


# --- Test calculate_required_parts ---


@pytest.fixture
def mock_get_recursive_bom(mocker: MockerFixture):
    """Fixture to mock the get_recursive_bom function."""

    # We need to simulate its side effect of populating the dict
    def side_effect_func(api, part_id, quantity, required_components_dict, root_input_id): # Add root_input_id
        # Simulate based on a predefined map for the test
        if part_id == 1000:  # Example target assembly
            required_components_dict[10] += 5.0 * quantity  # Requires 5 of part 10
            required_components_dict[11] += 2.0 * quantity  # Requires 2 of part 11
        elif part_id == 2000:  # Another target assembly
            required_components_dict[11] += 3.0 * quantity  # Requires 3 more of part 11
            required_components_dict[12] += 1.0 * quantity  # Requires 1 of part 12
        # Add more simulation logic if needed for other test cases

    return mocker.patch(
        "inventree_logic.get_recursive_bom", side_effect=side_effect_func
    )


# Fixture already added
@pytest.fixture
def mock_get_final_part_data(mocker: MockerFixture):
    """Fixture to mock the get_final_part_data function."""
    return mocker.patch("inventree_logic.get_final_part_data")
def mock_get_final_part_data(mocker: MockerFixture):
    """Fixture to mock the get_final_part_data function."""
    return mocker.patch("inventree_logic.get_final_part_data")


# Signature already updated
def test_calculate_required_parts_basic(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """Tests basic calculation where some parts need ordering."""
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {1000: 1.0}  # Request 1 of assembly 1000

    # Mock final data: Part 10 needs ordering, Part 11 is in stock
    mock_get_final_part_data.return_value = {
        10: {"name": "Part 10", "in_stock": 3.0},
        11: {"name": "Part 11", "in_stock": 50.0},
    }

    # Expected required based on mock_get_recursive_bom side effect for {1000: 1.0}
    # Part 10: 5.0 * 1.0 = 5.0
    # Part 11: 2.0 * 1.0 = 2.0

    expected_order_list = [
        {"pk": 10, "name": "Part 10", "required": 5.0, "in_stock": 3.0, "to_order": 2.0}
        # Part 11 not included as required (2.0) <= in_stock (50.0)
    ]

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    # Check mocks were called
    mock_get_recursive_bom.assert_called_once()
    # Check the defaultdict passed to recursive_bom (it's the 4th arg, index 3)
    call_args, _ = mock_get_recursive_bom.call_args
    final_required_dict = call_args[3]
    assert final_required_dict == {10: 5.0, 11: 2.0}

    # Check final data fetch (needs tuple of keys from the dict)
    mock_get_final_part_data.assert_called_once_with(
        mock_api_instance, tuple(sorted(final_required_dict.keys()))
    )

    # Check final result (order matters due to sort in original function)
    assert parts_to_order == expected_order_list


# Signature already updated
def test_calculate_required_parts_multiple_targets(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """Tests calculation with multiple target assemblies."""
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {1000: 2.0, 2000: 1.0}  # Request 2 of 1000, 1 of 2000

    # Mock final data
    mock_get_final_part_data.return_value = {
        10: {"name": "Part 10", "in_stock": 8.0},
        11: {"name": "Part 11", "in_stock": 5.0},
        12: {"name": "Part 12", "in_stock": 0.0},
    }

    # Expected required based on mock_get_recursive_bom side effect:
    # From {1000: 2.0}: Part 10 += 5.0*2.0=10.0, Part 11 += 2.0*2.0=4.0
    # From {2000: 1.0}: Part 11 += 3.0*1.0=3.0, Part 12 += 1.0*1.0=1.0
    # Total required: Part 10 = 10.0, Part 11 = 7.0, Part 12 = 1.0

    expected_order_list = [
        # Sorted by name
        {
            "pk": 10,
            "name": "Part 10",
            "required": 10.0,
            "in_stock": 8.0,
            "to_order": 2.0,
        },
        {
            "pk": 11,
            "name": "Part 11",
            "required": 7.0,
            "in_stock": 5.0,
            "to_order": 2.0,
        },
        {
            "pk": 12,
            "name": "Part 12",
            "required": 1.0,
            "in_stock": 0.0,
            "to_order": 1.0,
        },
    ]

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    assert mock_get_recursive_bom.call_count == 2
    call_args_list = mock_get_recursive_bom.call_args_list
    final_required_dict = call_args_list[-1][0][3]  # Get dict from last call
    assert final_required_dict == {10: 10.0, 11: 7.0, 12: 1.0}

    mock_get_final_part_data.assert_called_once_with(
        mock_api_instance, tuple(sorted(final_required_dict.keys()))
    )
    assert parts_to_order == expected_order_list


# Signature already updated
def test_calculate_required_parts_none_needed(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """Tests calculation where all parts are sufficiently in stock."""
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {1000: 1.0}

    # Mock final data: Plenty of stock (including new fields)
    mock_get_final_part_data.return_value = {
        10: {"name": "Part 10", "in_stock": 100.0, "is_template": False, "variant_stock": 0.0},
        11: {"name": "Part 11", "in_stock": 100.0, "is_template": False, "variant_stock": 0.0},
    }

    # Required: Part 10 = 5.0, Part 11 = 2.0 (from mock_get_recursive_bom)
    expected_order_list = []  # Empty list

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    assert mock_get_recursive_bom.call_count == 1
    final_required_dict = mock_get_recursive_bom.call_args[0][3]
    assert final_required_dict == {10: 5.0, 11: 2.0}
    mock_get_final_part_data.assert_called_once_with(
        mock_api_instance, tuple(sorted(final_required_dict.keys()))
    )
    assert parts_to_order == expected_order_list


def test_calculate_required_parts_empty_targets(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """Tests calculation with an empty target assemblies dictionary."""
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {}

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    mock_get_recursive_bom.assert_not_called()
    mock_get_final_part_data.assert_not_called()
    assert parts_to_order == []


# Signature already updated
def test_calculate_required_parts_final_data_fails(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """Tests calculation when get_final_part_data returns missing data."""
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {1000: 1.0}

    # Mock final data: Simulate failure for Part 10
    # Mock final data: Simulate failure for Part 10 (ensure Part 11 has new fields)
    mock_get_final_part_data.return_value = {
        # 10: Missing - function should provide defaults
        11: {"name": "Part 11", "in_stock": 1.0, "is_template": False, "variant_stock": 0.0} # Needs ordering
    }

    # Required: Part 10 = 5.0, Part 11 = 2.0
    expected_order_list = [
        # Sorted by name (Unknown comes after Part 11)
         {
            "pk": 11,
            "name": "Part 11",
            "total_required": 2.0, # Use total_required
            "in_stock": 1.0,
            "to_order": 1.0,
            "used_in_assemblies": "Assembly 1000", # Assuming mock name
            "purchase_orders": []
        },
        {
            "pk": 10,
            "name": "Unknown (ID: 10)",
            "total_required": 5.0, # Use total_required
            "in_stock": 0.0, # Default stock on failure
            "to_order": 5.0,
            "used_in_assemblies": "Assembly 1000", # Assuming mock name
            "purchase_orders": []
        }, # Fallback
    ]

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    assert mock_get_recursive_bom.call_count == 1
    final_required_dict = mock_get_recursive_bom.call_args[0][3]
    assert final_required_dict == {10: 5.0, 11: 2.0}
    mock_get_final_part_data.assert_called_once_with(
        mock_api_instance, tuple(sorted(final_required_dict.keys()))
    )
    # Sort the result for comparison as fallback names affect order
    assert sorted(parts_to_order, key=lambda x: x["pk"]) == sorted(
        expected_order_list, key=lambda x: x["pk"]
    )


def test_calculate_required_parts_invalid_api(
    mock_get_recursive_bom, mock_get_final_part_data
):
    """Tests calculation when the API object is None."""
    target_assemblies = {1000: 1.0}

    parts_to_order = calculate_required_parts(None, target_assemblies)

    mock_get_recursive_bom.assert_not_called()
    mock_get_final_part_data.assert_not_called()
    assert parts_to_order == []


# Signature already updated
def test_calculate_required_parts_float_tolerance(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """Tests that the float tolerance prevents ordering tiny amounts."""
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {1000: 1.0}  # Requires 5.0 of Part 10

    # Mock final data: Stock is *almost* enough
    mock_get_final_part_data.return_value = {
        10: {"name": "Part 10", "in_stock": 4.9995, "is_template": False, "variant_stock": 0.0},  # Difference is 0.0005
        11: {"name": "Part 11", "in_stock": 1.999, "is_template": False, "variant_stock": 0.0},  # Difference is 0.001
    }

    # Required: Part 10 = 5.0, Part 11 = 2.0
    # Part 10 to_order = 5.0 - 4.9995 = 0.0005 (<= 0.001, should NOT be ordered)
    # Part 11 to_order = 2.0 - 1.999 = 0.001 (<= 0.001, should NOT be ordered)

    expected_order_list = []  # Nothing should be ordered

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    assert mock_get_recursive_bom.call_count == 1
    final_required_dict = mock_get_recursive_bom.call_args[0][3]
    assert final_required_dict == {10: 5.0, 11: 2.0}
    mock_get_final_part_data.assert_called_once_with(
        mock_api_instance, tuple(sorted(final_required_dict.keys()))
    )
    assert parts_to_order == expected_order_list


# --- Tests for Variant Logic in calculate_required_parts ---

def test_calculate_required_parts_template_variants_allowed(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """
    Tests calculation when a template part is required, variants are allowed,
    and stock calculation should use template + variant stock.
    """
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {2000: 1.0} # Assembly requiring the template part

    template_part_id = 1001
    required_qty = 5.0

    # Mock get_recursive_bom to simulate requiring 5.0 of the template part
    # and importantly, NOT setting the template_only_flags for it.
    def recursive_bom_side_effect(api, part_id, quantity, req_dict, root_id, flags_dict):
        if part_id == 2000:
            req_dict[root_id][template_part_id] += quantity * required_qty
        # flags_dict remains empty as variants are allowed in this scenario's BOM path
    mock_get_recursive_bom.side_effect = recursive_bom_side_effect

    # Mock final data for the template part: Not enough in_stock alone, but enough with variant_stock
    mock_get_final_part_data.return_value = {
        template_part_id: {
            "name": "Template Part A",
            "in_stock": 2.0,
            "is_template": True,
            "variant_stock": 10.0 # 2 + 10 = 12.0 available > 5.0 required
        }
    }

    # Expected: No order needed as 2.0 + 10.0 >= 5.0
    expected_order_list = []

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    assert mock_get_recursive_bom.call_count == 1
    final_required_dict = mock_get_recursive_bom.call_args[0][3]
    assert final_required_dict == {template_part_id: required_qty}
    mock_get_final_part_data.assert_called_once_with(
        mock_api_instance, tuple(sorted(final_required_dict.keys()))
    )
    assert parts_to_order == expected_order_list


def test_calculate_required_parts_template_variants_disallowed(
    mock_api_class, mock_get_recursive_bom, mock_get_final_part_data
):
    """
    Tests calculation when a template part is required, variants were disallowed
    on the BOM line, and stock calculation should use ONLY template stock.
    """
    mock_api_instance = mock_api_class.return_value
    target_assemblies = {2001: 1.0} # Assembly requiring the template part

    template_part_id = 1002
    required_qty = 5.0

    # Mock get_recursive_bom to simulate requiring 5.0 of the template part
    # AND setting the template_only_flags for it.
    def recursive_bom_side_effect(api, part_id, quantity, req_dict, root_id, flags_dict):
        if part_id == 2001:
            req_dict[root_id][template_part_id] += quantity * required_qty
            # Simulate that the BOM traversal set the flag because allow_variants=False
            flags_dict[template_part_id] = True
    mock_get_recursive_bom.side_effect = recursive_bom_side_effect

    # Mock final data for the template part: Not enough in_stock alone, variant_stock is ignored
    mock_get_final_part_data.return_value = {
        template_part_id: {
            "name": "Template Part B",
            "in_stock": 2.0, # Available = 2.0
            "is_template": True,
            "variant_stock": 10.0 # This should be ignored
        }
    }

    # Expected: Order needed = Required (5.0) - Available (2.0) = 3.0
    expected_order_list = [
        {
            "pk": template_part_id,
            "name": "Template Part B",
            "total_required": 5.0,
            "in_stock": 2.0, # Report the template's stock
            "to_order": 3.0,
            "used_in_assemblies": "Assembly 2001", # Assuming mock name
            "purchase_orders": []
        }
    ]

    parts_to_order = calculate_required_parts(mock_api_instance, target_assemblies)

    assert mock_get_recursive_bom.call_count == 1
    final_required_dict = mock_get_recursive_bom.call_args[0][3]
    template_flags = mock_get_recursive_bom.call_args[0][5] # Get the flags dict passed
    assert final_required_dict == {template_part_id: required_qty}
    assert template_flags == {template_part_id: True} # Verify flag was set by mock
    mock_get_final_part_data.assert_called_once_with(
        mock_api_instance, tuple(sorted(final_required_dict.keys()))
    )
    assert parts_to_order == expected_order_list
