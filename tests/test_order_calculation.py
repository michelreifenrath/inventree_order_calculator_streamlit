import pytest
from unittest.mock import patch, MagicMock, call
from collections import defaultdict
from src.order_calculation import calculate_required_parts

# Mock data representing the output of get_final_part_data
# CORRECTED: Use supplier_names list instead of supplier_name string
MOCK_FINAL_PART_DATA = {
    10: {"pk": 10, "name": "Resistor R1", "in_stock": 50.0, "is_template": False, "variant_stock": 0.0, "supplier_names": ["Supplier A"], "manufacturer_name": "Manu X"},
    20: {"pk": 20, "name": "Capacitor C1", "in_stock": 100.0, "is_template": False, "variant_stock": 0.0, "supplier_names": ["HAIP Solutions GmbH", "Supplier C"], "manufacturer_name": "Manu Y"}, # Added another supplier
    30: {"pk": 30, "name": "IC U1", "in_stock": 10.0, "is_template": False, "variant_stock": 0.0, "supplier_names": ["Supplier B"], "manufacturer_name": "HAIP Solutions GmbH"}, # Test manufacturer exclusion
    40: {"pk": 40, "name": "Diode D1", "in_stock": 200.0, "is_template": False, "variant_stock": 0.0, "supplier_names": ["Supplier A"], "manufacturer_name": "Manu X"},
    50: {"pk": 50, "name": "Transistor Q1", "in_stock": 5.0, "is_template": False, "variant_stock": 0.0, "supplier_names": ["HAIP Solutions GmbH"], "manufacturer_name": "Manu Z"},
    99: {"pk": 99, "name": "Assembly Top", "in_stock": 0.0, "is_template": True, "variant_stock": 0.0, "supplier_names": [], "manufacturer_name": ""}, # Root assembly
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
# CORRECTED: Use supplier_names list
ADJUSTED_MOCK_FINAL_PART_DATA = {}
for pk, data in MOCK_FINAL_PART_DATA.items():
    ADJUSTED_MOCK_FINAL_PART_DATA[pk] = data.copy() # Start with a copy

ADJUSTED_MOCK_FINAL_PART_DATA[10]['in_stock'] = 2.0 # Req 5, Stock 2 -> Order 3
ADJUSTED_MOCK_FINAL_PART_DATA[30]['in_stock'] = 1.0 # Req 2, Stock 1 -> Order 1
ADJUSTED_MOCK_FINAL_PART_DATA[50]['in_stock'] = 0.0 # Req 1, Stock 0 -> Order 1


# Helper function to calculate available stock based on part data
def _calculate_available_stock(part_pk, part_data_dict):
    part_data = part_data_dict.get(part_pk)
    if not part_data:
        return 0.0
    in_stock = part_data.get("in_stock", 0.0)
    is_template = part_data.get("is_template", False)
    variant_stock = part_data.get("variant_stock", 0.0)
    # Mimic logic from calculate_required_parts for consistency
    if is_template:
        return in_stock + variant_stock
    else:
        return in_stock

# Modified mock side effect to simulate stock subtraction
def mock_get_bom_with_stock_subtraction(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs, part_data_source):
    """
    Simulates get_recursive_bom including stock subtraction.
    Adds the *net* required quantity to req_comps.
    Requires part_data_source (like ADJUSTED_MOCK_FINAL_PART_DATA) to be passed.
    req_comps dictionary based on MOCK_BOM_EFFECT.
    """
    bom_for_part = MOCK_BOM_EFFECT.get(part_id, {})
    for base_part_id, qty_per_assembly in bom_for_part.items():
        gross_required = qty_per_assembly * quantity_needed
        available_stock = _calculate_available_stock(base_part_id, part_data_source)
        net_required = max(0, gross_required - available_stock)

        if net_required > 0:
             req_comps[root_id][base_part_id] += net_required # Add NET quantity

        # Simulate tracking encountered parts
        encountered_ids.add(base_part_id)
    # Simulate tracking the assembly itself
    encountered_ids.add(part_id)
    # Simulate tracking assemblies (add root for simplicity in test)
    # In real code, this logic is more complex
    if part_data_source.get(part_id, {}).get("assembly", False):
         req_subs[root_id][part_id] += quantity_needed # Track the assembly itself if needed by caller logic


@pytest.fixture
def mock_api():
    """Provides a MagicMock instance for the InvenTreeAPI."""
    return MagicMock()

# --- Test Cases ---

@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_no_exclusions_with_stock_check(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """
    Test calculation ensuring stock is subtracted only once (in mock BOM).
    """
    # Setup Mocks
    # Use the mock that simulates stock subtraction
    mock_get_bom.side_effect = lambda api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs: \
        mock_get_bom_with_stock_subtraction(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs, ADJUSTED_MOCK_FINAL_PART_DATA)

    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA # Main function still needs this for display/filtering
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0} # Request 1 of Assembly 99
    parts_result, subs_result = calculate_required_parts(mock_api, target_assemblies) # Capture both results

    # Assertions
    # Expected Net Requirements (Gross Req - Stock):
    # Part 10: 5.0 - 2.0 = 3.0
    # Part 20: 10.0 - 100.0 = 0.0 (Not ordered)
    # Part 30: 2.0 - 1.0 = 1.0
    # Part 40: 8.0 - 200.0 = 0.0 (Not ordered)
    # Part 50: 1.0 - 0.0 = 1.0
    assert len(parts_result) == 3 # Parts 10, 30, 50 need ordering based on NET requirement
    part_ids_in_result = {p['pk'] for p in parts_result}
    assert part_ids_in_result == {10, 30, 50} # Check correct parts are present

    part10 = next(p for p in parts_result if p['pk'] == 10)
    assert part10['total_required'] == 3.0 # Should reflect NET requirement
    assert part10['available_stock'] == 2.0 # Displayed stock
    assert part10['to_order'] == 3.0 # Should equal NET requirement
    assert part10['purchase_orders'] == MOCK_PO_DATA[10]

    part30 = next(p for p in parts_result if p['pk'] == 30)
    assert part30['total_required'] == 1.0 # Should reflect NET requirement
    assert part30['available_stock'] == 1.0 # Displayed stock
    assert part30['to_order'] == 1.0 # Should equal NET requirement
    assert part30['purchase_orders'] == MOCK_PO_DATA[30]

    part50 = next(p for p in parts_result if p['pk'] == 50)
    assert part50['total_required'] == 1.0 # Should reflect NET requirement
    assert part50['available_stock'] == 0.0 # Displayed stock
    assert part50['to_order'] == 1.0 # Should equal NET requirement
    assert part50['purchase_orders'] == []

    assert not subs_result # No sub-assemblies expected in this simple test structure


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_supplier(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when excluding a supplier."""
    # Setup Mocks with adjusted stock - USE NEW MOCK BOM
    mock_get_bom.side_effect = lambda api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs: \
        mock_get_bom_with_stock_subtraction(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs, ADJUSTED_MOCK_FINAL_PART_DATA)
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    supplier_to_exclude = "HAIP Solutions GmbH" # Matches Part 20 (not ordered) and Part 50 (ordered)

    parts_result, subs_result = calculate_required_parts( # Capture both results
        mock_api,
        target_assemblies,
        exclude_supplier_name=supplier_to_exclude
    )

    # Assertions
    assert len(parts_result) == 2 # Part 50 (Supplier HAIP) should be excluded
    part_ids_in_result = {p['pk'] for p in parts_result}
    assert part_ids_in_result == {10, 30} # Only parts 10 and 30 remain
    assert not subs_result # No sub-assemblies expected


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_manufacturer(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when excluding a manufacturer."""
    # Setup Mocks with adjusted stock - USE NEW MOCK BOM
    mock_get_bom.side_effect = lambda api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs: \
        mock_get_bom_with_stock_subtraction(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs, ADJUSTED_MOCK_FINAL_PART_DATA)
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    manufacturer_to_exclude = "HAIP Solutions GmbH" # Matches Part 30 (ordered)

    parts_result, subs_result = calculate_required_parts( # Capture both results
        mock_api,
        target_assemblies,
        exclude_manufacturer_name=manufacturer_to_exclude
    )

    # Assertions
    assert len(parts_result) == 2 # Part 30 (Manufacturer HAIP) should be excluded
    part_ids_in_result = {p['pk'] for p in parts_result}
    assert part_ids_in_result == {10, 50} # Only parts 10 and 50 remain
    assert not subs_result # No sub-assemblies expected


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_both(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when excluding both a supplier and a manufacturer."""
    # Setup Mocks with adjusted stock - USE NEW MOCK BOM
    mock_get_bom.side_effect = lambda api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs: \
        mock_get_bom_with_stock_subtraction(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs, ADJUSTED_MOCK_FINAL_PART_DATA)
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    supplier_to_exclude = "HAIP Solutions GmbH" # Matches Part 50
    manufacturer_to_exclude = "HAIP Solutions GmbH" # Matches Part 30

    parts_result, subs_result = calculate_required_parts( # Capture both results
        mock_api,
        target_assemblies,
        exclude_supplier_name=supplier_to_exclude,
        exclude_manufacturer_name=manufacturer_to_exclude
    )

    # Assertions
    assert len(parts_result) == 1 # Parts 30 and 50 should be excluded
    part_ids_in_result = {p['pk'] for p in parts_result}
    assert part_ids_in_result == {10} # Only part 10 remains
    assert not subs_result # No sub-assemblies expected


@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_exclude_no_match(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation when exclusion names don't match any parts."""
    # Setup Mocks with adjusted stock - USE NEW MOCK BOM
    mock_get_bom.side_effect = lambda api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs: \
        mock_get_bom_with_stock_subtraction(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs, ADJUSTED_MOCK_FINAL_PART_DATA)
    mock_get_final_data.return_value = ADJUSTED_MOCK_FINAL_PART_DATA
    mock_fetch_po.return_value = MOCK_PO_DATA

    target_assemblies = {99: 1.0}
    supplier_to_exclude = "NonExistent Supplier"
    manufacturer_to_exclude = "NonExistent Manufacturer"

    parts_result, subs_result = calculate_required_parts( # Capture both results
        mock_api,
        target_assemblies,
        exclude_supplier_name=supplier_to_exclude,
        exclude_manufacturer_name=manufacturer_to_exclude
    )

    # Assertions
    assert len(parts_result) == 3 # No parts should be excluded
    part_ids_in_result = {p['pk'] for p in parts_result}
    assert part_ids_in_result == {10, 30, 50}
    assert not subs_result # No sub-assemblies expected


# --- Edge Case and Failure Tests (Kept from original, adapted slightly) ---

def test_calculate_required_parts_edge_case_empty_targets(mock_api):
    """Edge Case: Empty target_assemblies dictionary."""
    parts_result, subs_result = calculate_required_parts( # Capture both results
        mock_api,
        target_assemblies={},
    )
    assert parts_result == [] # Check parts list
    assert subs_result == [] # Check sub-assembly list


def test_calculate_required_parts_failure_no_api():
    """Failure Case: API object is None."""
    parts_result, subs_result = calculate_required_parts( # Capture both results
        None, # Pass None for API
        target_assemblies={1: 1},
    )
    assert parts_result == [] # Check parts list
    assert subs_result == [] # Check sub-assembly list

# --- Test for Template Part with Variant Stock ---

@patch('src.order_calculation.get_recursive_bom')
@patch('src.order_calculation.get_final_part_data')
@patch('src.order_calculation._fetch_purchase_order_data')
def test_template_part_with_variant_stock(mock_fetch_po, mock_get_final_data, mock_get_bom, mock_api):
    """Test calculation involving a template part with variant stock."""
    # --- Mock Data Setup ---
    # Base data (can reuse parts of ADJUSTED_MOCK_FINAL_PART_DATA)
    test_part_data = {
        # Template part with variant stock
        60: {"pk": 60, "name": "Template Widget", "in_stock": 5.0, "is_template": True, "variant_stock": 10.0, "supplier_names": [], "manufacturer_name": None},
        # Root assembly needing the template part
        100: {"pk": 100, "name": "Root Assembly B", "in_stock": 0.0, "is_template": True, "variant_stock": 0.0, "supplier_names": [], "manufacturer_name": None},
    }

    # Mock BOM effect: Root Assembly 100 needs 20 of Template Widget 60
    test_bom_effect = {
        100: {
            60: 20.0
        }
    }

    # Mock PO data (empty for this test)
    test_po_data = {}

    # --- Mock Function Behavior ---
    # Use the mock that simulates stock subtraction for this specific test data
    mock_get_bom.side_effect = lambda api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs: \
        mock_get_bom_with_stock_subtraction(api, part_id, quantity_needed, req_comps, root_id, tmpl_flags, encountered_ids, req_subs, test_part_data)

    mock_get_final_data.return_value = test_part_data # Main function still needs this
    mock_fetch_po.return_value = test_po_data

    # --- Run Calculation ---
    target_assemblies = {100: 1.0} # Request 1 of Root Assembly B
    parts_result, subs_result = calculate_required_parts(mock_api, target_assemblies) # Capture both results

    # --- Assertions ---
    # Expected available stock for part 60 = in_stock (5.0) + variant_stock (10.0) = 15.0
    # Required = 20.0
    # Expected Net Requirement: Gross Req (20.0) - Available Stock (5.0 + 10.0 = 15.0) = 5.0
    assert len(parts_result) == 1 # Only part 60 should need ordering
    part60 = parts_result[0]
    assert part60['pk'] == 60
    assert part60['total_required'] == 5.0 # Should reflect NET requirement
    assert part60['available_stock'] == 15.0 # Displayed stock (in_stock + variant_stock)
    assert part60['to_order'] == 5.0 # Should equal NET requirement
    assert not subs_result # No sub-assemblies expected in this simple test
