import pytest
from unittest.mock import patch, MagicMock, call
from collections import defaultdict
from src.order_calculation import calculate_required_parts

# Mock data representing the output of get_final_part_data
MOCK_FINAL_PART_DATA = {
    10: {"pk": 10, "name": "Resistor R1", "in_stock": 50.0, "is_template": False, "variant_stock": 0.0, "supplier_name": "Supplier A", "manufacturer_name": "Manu X"},
    20: {"pk": 20, "name": "Capacitor C1", "in_stock": 100.0, "is_template": False, "variant_stock": 0.0, "supplier_name": "HAIP Solutions GmbH", "manufacturer_name": "Manu Y"},
    30: {"pk": 30, "name": "IC U1", "in_stock": 10.0, "is_template": False, "variant_stock": 0.0, "supplier_name": "Supplier B", "manufacturer_name": "HAIP Solutions GmbH"}, # Test manufacturer exclusion
    40: {"pk": 40, "name": "Diode D1", "in_stock": 200.0, "is_template": False, "variant_stock": 0.0, "supplier_name": "Supplier A", "manufacturer_name": "Manu X"},
    50: {"pk": 50, "name": "Transistor Q1", "in_stock": 5.0, "is_template": False, "variant_stock": 0.0, "supplier_name": "HAIP Solutions GmbH", "manufacturer_name": "Manu Z"},
    99: {"pk": 99, "name": "Assembly Top", "in_stock": 0.0, "is_template": True, "variant_stock": 0.0, "supplier_name": "", "manufacturer_name": ""}, # Root assembly
}

# Mock data representing the *effect* of get_recursive_bom on required_base_components
# Structure: MOCK_BOM_EFFECT[root_assembly_id][base_part_id] = quantity_per_root_assembly
MOCK_BOM_EFFECT = {
    99: {
        10: 5.0,  # Assembly 99 needs 5 of Part 10
        20: 10.0, # Assembly 99 needs 10 of Part 20
        30: 2.0,  # Assembly 99 needs 2 of Part 30
        40: 8.0,  # Assembly 99 needs 8 of Part 40
        50: 1.0,  # Assembly 99 needs 1 of Part 50
    }
}

# Mock data representing the output of _fetch_purchase_order_data
MOCK_PO_DATA = {
    10: [{"quantity": 5.0, "po_ref": "PO-001", "po_status": "Placed"}],
    # Part 20 has no POs
    30: [{"quantity": 10.0, "po_ref": "PO-002", "po_status": "Pending"}],
}

# Adjusted stock levels to force ordering in tests
ADJUSTED_MOCK_FINAL_PART_DATA = MOCK_FINAL_PART_DATA.copy()
ADJUSTED_MOCK_FINAL_PART_DATA[10] = {**MOCK_FINAL_PART_DATA[10], 'in_stock': 2.0} # Req 5, Stock 2 -> Order 3
ADJUSTED_MOCK_FINAL_PART_DATA[30] = {**MOCK_FINAL_PART_DATA[30], 'in_stock': 1.0} # Req 2, Stock 1 -> Order 1
ADJUSTED_MOCK_FINAL_PART_DATA[50] = {**MOCK_FINAL_PART_DATA[50], 'in_stock': 0.0} # Req 1, Stock 0 -> Order 1


def mock_get_bom_side_effect(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids):
    """
    Simulates the effect of get_recursive_bom by modifying the
    req_comps dictionary based on MOCK_BOM_EFFECT.
    """
    # Find the base components required for the current part_id (which is the root_id in our simple test case)
    bom_for_part = MOCK_BOM_EFFECT.get(part_id, {})
    for base_part_id, qty_per_assembly in bom_for_part.items():
        # Add the calculated quantity to the dictionary passed in (req_comps)
        # The key is the *original* root assembly ID requested by the user
        req_comps[root_id][base_part_id] += qty_per_assembly * quantity_needed
        # Simulate tracking encountered parts
        encountered_ids.add(base_part_id)
    # Simulate tracking the assembly itself
    encountered_ids.add(part_id)


@pytest.fixture
def mock_api():
    """Provides a MagicMock instance for the InvenTreeAPI."""
    return MagicMock()

# --- Test Cases ---

@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_no_exclusions(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when no exclusions are applied."""
    # Setup Mocks
    mock_get_bom.side_effect = mock_get_bom_side_effect # Use the new side effect function
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA # Use adjusted stock
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0} # Request 1 of Assembly 99
    result = calculate_required_parts(mock_api, target_assemblies)

    # Assertions
    assert len(result) == 3 # Parts 10, 30, 50 need ordering
    part_ids_in_result = {p['pk'] for p in result}
    assert part_ids_in_result == {10, 30, 50} # Check correct parts are present

    part10 = next(p for p in result if p['pk'] == 10)
    assert part10['to_order'] == 3.0
    assert part10['purchase_orders'] == MOCK_PO_DATA[10] # Check PO data attached

    part30 = next(p for p in result if p['pk'] == 30)
    assert part30['to_order'] == 1.0
    assert part30['purchase_orders'] == MOCK_PO_DATA[30]

    part50 = next(p for p in result if p['pk'] == 50)
    assert part50['to_order'] == 1.0
    assert part50['purchase_orders'] == [] # No PO data for part 50


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_supplier(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when excluding a supplier."""
    # Setup Mocks with adjusted stock
    mock_get_bom.side_effect = mock_get_bom_side_effect
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    supplier_to_exclude = "HAIP Solutions GmbH" # Matches Part 20 (not ordered) and Part 50 (ordered)

    result = calculate_required_parts(
        mock_api,
        target_assemblies,
        exclude_supplier_name=supplier_to_exclude
    )

    # Assertions
    assert len(result) == 2 # Part 50 (Supplier HAIP) should be excluded
    part_ids_in_result = {p['pk'] for p in result}
    assert part_ids_in_result == {10, 30} # Only parts 10 and 30 remain


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_manufacturer(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when excluding a manufacturer."""
    # Setup Mocks with adjusted stock
    mock_get_bom.side_effect = mock_get_bom_side_effect
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    manufacturer_to_exclude = "HAIP Solutions GmbH" # Matches Part 30 (ordered)

    result = calculate_required_parts(
        mock_api,
        target_assemblies,
        exclude_manufacturer_name=manufacturer_to_exclude
    )

    # Assertions
    assert len(result) == 2 # Part 30 (Manufacturer HAIP) should be excluded
    part_ids_in_result = {p['pk'] for p in result}
    assert part_ids_in_result == {10, 50} # Only parts 10 and 50 remain


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_both(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when excluding both a supplier and a manufacturer."""
    # Setup Mocks with adjusted stock
    mock_get_bom.side_effect = mock_get_bom_side_effect
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    supplier_to_exclude = "HAIP Solutions GmbH" # Matches Part 50
    manufacturer_to_exclude = "HAIP Solutions GmbH" # Matches Part 30

    result = calculate_required_parts(
        mock_api,
        target_assemblies,
        exclude_supplier_name=supplier_to_exclude,
        exclude_manufacturer_name=manufacturer_to_exclude
    )

    # Assertions
    assert len(result) == 1 # Parts 30 and 50 should be excluded
    part_ids_in_result = {p['pk'] for p in result}
    assert part_ids_in_result == {10} # Only part 10 remains


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_no_match(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when exclusion names don't match any parts."""
    # Setup Mocks with adjusted stock
    mock_get_bom.side_effect = mock_get_bom_side_effect
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    supplier_to_exclude = "NonExistent Supplier"
    manufacturer_to_exclude = "NonExistent Manufacturer"

    result = calculate_required_parts(
        mock_api,
        target_assemblies,
        exclude_supplier_name=supplier_to_exclude,
        exclude_manufacturer_name=manufacturer_to_exclude
    )

    # Assertions
    assert len(result) == 3 # No parts should be excluded
    part_ids_in_result = {p['pk'] for p in result}
    assert part_ids_in_result == {10, 30, 50}


# --- Edge Case and Failure Tests (Kept from original, adapted slightly) ---

def test_calculate_required_parts_edge_case_empty_targets(mock_api):
    """Edge Case: Empty target_assemblies dictionary."""
    result = calculate_required_parts(
        mock_api,
        target_assemblies={},
    )
    assert result == []


def test_calculate_required_parts_failure_no_api():
    """Failure Case: API object is None."""
    result = calculate_required_parts(
        None, # Pass None for API
        target_assemblies={1: 1},
    )
    assert result == []
