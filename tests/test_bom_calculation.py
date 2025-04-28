import pytest
from collections import defaultdict
from unittest.mock import patch, MagicMock
from src.bom_calculation import get_recursive_bom # Import from src


# Keep DummyAPI for existing basic tests if needed, but new tests will use mocks
class DummyAPI:
    pass  # Mock API object


@pytest.fixture
def dummy_api():
    return DummyAPI()


# --- Existing Basic Tests (Keep them for now) ---

def test_recursive_bom_normal(dummy_api):
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    # This test doesn't actually verify logic due to DummyAPI
    # Consider removing or enhancing later if focusing on integration tests
    with patch('src.bom_calculation.get_part_details') as mock_details, \
         patch('src.bom_calculation.get_bom_items') as mock_bom:
        # Setup basic mocks to avoid errors even with DummyAPI
        mock_details.return_value = {'assembly': False, 'name': 'Dummy', 'in_stock': 0, 'variant_stock': 0, 'is_template': False}
        mock_bom.return_value = []

        get_recursive_bom(
            dummy_api, part_id=1, quantity=2, required_components=required,
            root_input_id=1, template_only_flags=template_flags,
            all_encountered_part_ids=encountered
        )
    assert isinstance(required, dict) # Basic check


def test_recursive_bom_edge_case(dummy_api):
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    with patch('src.bom_calculation.get_part_details') as mock_details, \
         patch('src.bom_calculation.get_bom_items') as mock_bom:
        mock_details.return_value = {'assembly': False, 'name': 'Dummy', 'in_stock': 0, 'variant_stock': 0, 'is_template': False}
        mock_bom.return_value = []

        get_recursive_bom(
            dummy_api, part_id=1, quantity=0, required_components=required,
            root_input_id=1, template_only_flags=template_flags,
            all_encountered_part_ids=encountered
        )
    assert not required[1] # Expect empty requirements for quantity 0


def test_recursive_bom_failure(dummy_api):
    # Test with None API should ideally raise specific error, but current code handles it
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    # No patching needed as the function should handle None API early
    get_recursive_bom(
        None, part_id=1, quantity=1, required_components=required,
        root_input_id=1, template_only_flags=template_flags,
        all_encountered_part_ids=encountered
    )
    # If it reaches here without error (due to logging/returning), check no reqs added
    assert not required[1]


# --- New Test for Variant Stock Handling ---

@patch('src.bom_calculation.get_bom_items')
@patch('src.bom_calculation.get_part_details')
def test_recursive_bom_base_component_with_variant_stock(mock_get_part_details, mock_get_bom_items, dummy_api):
    """
    Tests that base component requirements correctly account for in_stock and variant_stock
    when allow_variants is True.
    """
    # --- Mock Setup ---
    assembly_id = 100
    base_component_id = 101
    root_id = assembly_id
    required_assembly_qty = 10.0
    bom_qty_per_assembly = 2.0 # Need 2 base components per assembly
    base_in_stock = 5.0
    base_variant_stock = 8.0 # Total available = 13.0
    raw_total_required = required_assembly_qty * bom_qty_per_assembly # 10 * 2 = 20.0
    expected_net_required = max(0, raw_total_required - (base_in_stock + base_variant_stock)) # max(0, 20 - 13) = 7.0

    # Mock responses for the API helper functions
    def part_details_side_effect(api, part_id):
        if part_id == assembly_id:
            return {'pk': assembly_id, 'name': 'Test Assembly', 'assembly': True, 'in_stock': 0, 'variant_stock': 0, 'is_template': False}
        elif part_id == base_component_id:
            return {'pk': base_component_id, 'name': 'Base Component', 'assembly': False, 'in_stock': base_in_stock, 'variant_stock': base_variant_stock, 'is_template': False}
        else:
            return None # Should not happen in this test

    def bom_items_side_effect(api, part_id):
        if part_id == assembly_id:
            return [{'sub_part': base_component_id, 'quantity': bom_qty_per_assembly, 'allow_variants': True}]
        else:
            return [] # Base component has no BOM

    mock_get_part_details.side_effect = part_details_side_effect
    mock_get_bom_items.side_effect = bom_items_side_effect

    # --- Test Execution ---
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    sub_assemblies = defaultdict(lambda: defaultdict(float)) # Pass explicitly

    get_recursive_bom(
        api=dummy_api, # API object isn't really used due to mocks
        part_id=assembly_id,
        quantity=required_assembly_qty,
        required_components=required,
        root_input_id=root_id,
        template_only_flags=template_flags,
        all_encountered_part_ids=encountered,
        sub_assemblies=sub_assemblies
    )

    # --- Assertions ---
    # Check that the correct net quantity was added for the base component
    assert root_id in required
    assert base_component_id in required[root_id]
    assert required[root_id][base_component_id] == pytest.approx(expected_net_required)
    # Check that the base component wasn't treated as a sub-assembly
    assert base_component_id not in sub_assemblies[root_id]
    # Check encountered parts
    assert encountered == {assembly_id, base_component_id}


@patch('src.bom_calculation.get_bom_items')
@patch('src.bom_calculation.get_part_details')
def test_recursive_bom_base_component_variants_not_allowed(mock_get_part_details, mock_get_bom_items, dummy_api):
    """
    Tests that base component requirements correctly account ONLY for in_stock
    when allow_variants is False.
    """
    # --- Mock Setup ---
    assembly_id = 200
    base_component_id = 201
    root_id = assembly_id
    required_assembly_qty = 5.0
    bom_qty_per_assembly = 3.0 # Need 3 base components per assembly
    base_in_stock = 4.0
    base_variant_stock = 10.0 # Should be ignored
    raw_total_required = required_assembly_qty * bom_qty_per_assembly # 5 * 3 = 15.0
    expected_net_required = max(0, raw_total_required - base_in_stock) # max(0, 15 - 4) = 11.0

    def part_details_side_effect(api, part_id):
        if part_id == assembly_id:
            return {'pk': assembly_id, 'name': 'Test Assembly 2', 'assembly': True, 'in_stock': 0, 'variant_stock': 0, 'is_template': False}
        elif part_id == base_component_id:
            return {'pk': base_component_id, 'name': 'Base Component 2', 'assembly': False, 'in_stock': base_in_stock, 'variant_stock': base_variant_stock, 'is_template': False}
        return None

    def bom_items_side_effect(api, part_id):
        if part_id == assembly_id:
            # IMPORTANT: allow_variants is False
            return [{'sub_part': base_component_id, 'quantity': bom_qty_per_assembly, 'allow_variants': False}]
        return []

    mock_get_part_details.side_effect = part_details_side_effect
    mock_get_bom_items.side_effect = bom_items_side_effect

    # --- Test Execution ---
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    sub_assemblies = defaultdict(lambda: defaultdict(float))

    get_recursive_bom(
        api=dummy_api, part_id=assembly_id, quantity=required_assembly_qty,
        required_components=required, root_input_id=root_id,
        template_only_flags=template_flags, all_encountered_part_ids=encountered,
        sub_assemblies=sub_assemblies
    )

    # --- Assertions ---
    assert root_id in required
    assert base_component_id in required[root_id]
    assert required[root_id][base_component_id] == pytest.approx(expected_net_required)
    assert base_component_id not in sub_assemblies[root_id]
    assert encountered == {assembly_id, base_component_id}

# --- Tests for Sub-Assembly Stock Calculation ---

@patch('src.bom_calculation.get_bom_items')
@patch('src.bom_calculation.get_part_details')
def test_sub_assembly_stock_variants_allowed(mock_get_part_details, mock_get_bom_items, dummy_api):
    """
    Tests that sub-assembly stock (in_stock + variant_stock) is correctly used
    to reduce the 'to_build' quantity when the parent BOM item has allow_variants=True.
    """
    # --- Mock Setup ---
    top_assembly_id = 300
    sub_assembly_id = 301
    base_component_id = 302
    root_id = top_assembly_id

    required_top_qty = 10.0
    sub_assy_per_top = 1.0 # Need 1 sub-assembly per top assembly
    base_per_sub_assy = 2.0 # Need 2 base components per sub-assembly

    sub_assy_in_stock = 3.0
    sub_assy_variant_stock = 4.0 # Total available = 7.0
    base_comp_in_stock = 0.0 # Assume no stock of base component for simplicity

    # Calculations
    total_sub_assy_required = required_top_qty * sub_assy_per_top # 10 * 1 = 10.0
    # Since allow_variants=True for sub-assembly line, use both stock types
    available_sub_assy_stock = sub_assy_in_stock + sub_assy_variant_stock # 3 + 4 = 7.0
    sub_assy_to_build = max(0, total_sub_assy_required - available_sub_assy_stock) # max(0, 10 - 7) = 3.0
    # The BOM recursion for sub_assembly should only need to cover the 'to_build' quantity
    expected_base_comp_required = sub_assy_to_build * base_per_sub_assy # 3.0 * 2.0 = 6.0

    def part_details_side_effect(api, part_id):
        if part_id == top_assembly_id:
            return {'pk': top_assembly_id, 'name': 'Top Assembly', 'assembly': True, 'in_stock': 0, 'variant_stock': 0, 'is_template': False}
        elif part_id == sub_assembly_id:
            return {'pk': sub_assembly_id, 'name': 'Sub Assembly', 'assembly': True, 'in_stock': sub_assy_in_stock, 'variant_stock': sub_assy_variant_stock, 'is_template': False}
        elif part_id == base_component_id:
            return {'pk': base_component_id, 'name': 'Base Comp', 'assembly': False, 'in_stock': base_comp_in_stock, 'variant_stock': 0, 'is_template': False}
        return None

    def bom_items_side_effect(api, part_id):
        if part_id == top_assembly_id:
            # Sub-assembly line allows variants
            return [{'sub_part': sub_assembly_id, 'quantity': sub_assy_per_top, 'allow_variants': True}]
        elif part_id == sub_assembly_id:
            # Base component line in sub-assembly BOM (allow_variants doesn't matter here for calculation, only for base stock)
            return [{'sub_part': base_component_id, 'quantity': base_per_sub_assy, 'allow_variants': False}] # Set to False for base comp stock check
        return []

    mock_get_part_details.side_effect = part_details_side_effect
    mock_get_bom_items.side_effect = bom_items_side_effect

    # --- Test Execution ---
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    sub_assemblies = defaultdict(lambda: defaultdict(float))

    get_recursive_bom(
        api=dummy_api, part_id=top_assembly_id, quantity=required_top_qty,
        required_components=required, root_input_id=root_id,
        template_only_flags=template_flags, all_encountered_part_ids=encountered,
        sub_assemblies=sub_assemblies
    )

    # --- Assertions ---
    assert root_id in required
    assert base_component_id in required[root_id]
    # Verify the final required quantity of the base component matches the expectation based on sub_assy_to_build
    assert required[root_id][base_component_id] == pytest.approx(expected_base_comp_required)
    # Verify the sub-assembly itself was tracked correctly
    assert root_id in sub_assemblies
    assert sub_assembly_id in sub_assemblies[root_id]
    assert sub_assemblies[root_id][sub_assembly_id] == pytest.approx(total_sub_assy_required) # Tracks total needed before stock
    assert encountered == {top_assembly_id, sub_assembly_id, base_component_id}


@patch('src.bom_calculation.get_bom_items')
@patch('src.bom_calculation.get_part_details')
def test_sub_assembly_stock_variants_not_allowed(mock_get_part_details, mock_get_bom_items, dummy_api):
    """
    Tests that only sub-assembly in_stock is used to reduce the 'to_build'
    quantity when the parent BOM item has allow_variants=False.
    """
    # --- Mock Setup ---
    top_assembly_id = 400
    sub_assembly_id = 401
    base_component_id = 402
    root_id = top_assembly_id

    required_top_qty = 12.0
    sub_assy_per_top = 1.0
    base_per_sub_assy = 3.0

    sub_assy_in_stock = 5.0
    sub_assy_variant_stock = 10.0 # Should be ignored for 'to_build' calculation
    base_comp_in_stock = 0.0

    # Calculations
    total_sub_assy_required = required_top_qty * sub_assy_per_top # 12 * 1 = 12.0
    # Since allow_variants=False for sub-assembly line, use only in_stock
    available_sub_assy_stock = sub_assy_in_stock # Only 5.0
    sub_assy_to_build = max(0, total_sub_assy_required - available_sub_assy_stock) # max(0, 12 - 5) = 7.0
    # The BOM recursion for sub_assembly should only need to cover this 'to_build' quantity
    expected_base_comp_required = sub_assy_to_build * base_per_sub_assy # 7.0 * 3.0 = 21.0

    def part_details_side_effect(api, part_id):
        if part_id == top_assembly_id:
            return {'pk': top_assembly_id, 'name': 'Top Assembly 2', 'assembly': True, 'in_stock': 0, 'variant_stock': 0, 'is_template': False}
        elif part_id == sub_assembly_id:
            return {'pk': sub_assembly_id, 'name': 'Sub Assembly 2', 'assembly': True, 'in_stock': sub_assy_in_stock, 'variant_stock': sub_assy_variant_stock, 'is_template': False}
        elif part_id == base_component_id:
            return {'pk': base_component_id, 'name': 'Base Comp 2', 'assembly': False, 'in_stock': base_comp_in_stock, 'variant_stock': 0, 'is_template': False}
        return None

    def bom_items_side_effect(api, part_id):
        if part_id == top_assembly_id:
            # Sub-assembly line DOES NOT allow variants
            return [{'sub_part': sub_assembly_id, 'quantity': sub_assy_per_top, 'allow_variants': False}]
        elif part_id == sub_assembly_id:
            return [{'sub_part': base_component_id, 'quantity': base_per_sub_assy, 'allow_variants': False}]
        return []

    mock_get_part_details.side_effect = part_details_side_effect
    mock_get_bom_items.side_effect = bom_items_side_effect

    # --- Test Execution ---
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    sub_assemblies = defaultdict(lambda: defaultdict(float))

    get_recursive_bom(
        api=dummy_api, part_id=top_assembly_id, quantity=required_top_qty,
        required_components=required, root_input_id=root_id,
        template_only_flags=template_flags, all_encountered_part_ids=encountered,
        sub_assemblies=sub_assemblies
    )

    # --- Assertions ---
    assert root_id in required
    assert base_component_id in required[root_id]
    # Verify the final required quantity reflects the 'to_build' based only on in_stock
    assert required[root_id][base_component_id] == pytest.approx(expected_base_comp_required)
    assert root_id in sub_assemblies
    assert sub_assembly_id in sub_assemblies[root_id]
    assert sub_assemblies[root_id][sub_assembly_id] == pytest.approx(total_sub_assy_required)
    assert encountered == {top_assembly_id, sub_assembly_id, base_component_id}
# --- Test for Multi-Level Variant Handling ---

@patch('src.bom_calculation.get_bom_items')
@patch('src.bom_calculation.get_part_details')
def test_recursive_bom_multi_level_variants(mock_get_part_details, mock_get_bom_items, dummy_api):
    """
    Tests a multi-level BOM (Top -> Sub -> Base) where allow_variants differs
    at each level, verifying correct stock calculation propagation.

    Scenario:
    - Top (500) needs 10 units.
    - Top BOM: 1x Sub (501), allow_variants=True
    - Sub (501) Stock: in_stock=3, variant_stock=4 (Available for Top = 3+4=7)
    - Sub BOM: 2x Base (502), allow_variants=False
    - Base (502) Stock: in_stock=5, variant_stock=20 (Available for Sub = 5)

    Calculation:
    1. Need 10 * 1 = 10 Sub(501).
    2. Available Sub(501) stock (variants allowed) = 3 + 4 = 7.
    3. Need to build Sub(501) = 10 - 7 = 3.
    4. These 3 Sub(501) require 3 * 2 = 6 Base(502).
    5. Available Base(502) stock (variants NOT allowed) = 5.
    6. Net Base(502) required = max(0, 6 - 5) = 1.
    """
    # --- Mock Setup ---
    top_assembly_id = 500
    sub_assembly_id = 501
    base_component_id = 502
    root_id = top_assembly_id

    required_top_qty = 10.0
    sub_assy_per_top = 1.0
    base_per_sub_assy = 2.0

    sub_assy_in_stock = 3.0
    sub_assy_variant_stock = 4.0
    base_comp_in_stock = 5.0
    base_comp_variant_stock = 20.0

    expected_net_base_required = 1.0

    def part_details_side_effect(api, part_id):
        if part_id == top_assembly_id:
            return {'pk': top_assembly_id, 'name': 'Top Multi', 'assembly': True, 'in_stock': 0, 'variant_stock': 0, 'is_template': False}
        elif part_id == sub_assembly_id:
            return {'pk': sub_assembly_id, 'name': 'Sub Multi', 'assembly': True, 'in_stock': sub_assy_in_stock, 'variant_stock': sub_assy_variant_stock, 'is_template': False}
        elif part_id == base_component_id:
            return {'pk': base_component_id, 'name': 'Base Multi', 'assembly': False, 'in_stock': base_comp_in_stock, 'variant_stock': base_comp_variant_stock, 'is_template': False}
        return None

    def bom_items_side_effect(api, part_id):
        if part_id == top_assembly_id:
            # Top -> Sub link: Allow Variants TRUE
            return [{'sub_part': sub_assembly_id, 'quantity': sub_assy_per_top, 'allow_variants': True}]
        elif part_id == sub_assembly_id:
            # Sub -> Base link: Allow Variants FALSE
            return [{'sub_part': base_component_id, 'quantity': base_per_sub_assy, 'allow_variants': False}]
        return []

    mock_get_part_details.side_effect = part_details_side_effect
    mock_get_bom_items.side_effect = bom_items_side_effect

    # --- Test Execution ---
    required = defaultdict(lambda: defaultdict(float))
    template_flags = defaultdict(bool)
    encountered = set()
    sub_assemblies = defaultdict(lambda: defaultdict(float))

    get_recursive_bom(
        api=dummy_api, part_id=top_assembly_id, quantity=required_top_qty,
        required_components=required, root_input_id=root_id,
        template_only_flags=template_flags, all_encountered_part_ids=encountered,
        sub_assemblies=sub_assemblies
    )

    # --- Assertions ---
    assert root_id in required
    assert base_component_id in required[root_id]
    # Verify the final required quantity of the base component matches the multi-level calculation
    assert required[root_id][base_component_id] == pytest.approx(expected_net_base_required)

    # Optional: Verify intermediate tracking if needed
    assert root_id in sub_assemblies
    assert sub_assembly_id in sub_assemblies[root_id]
    assert sub_assemblies[root_id][sub_assembly_id] == pytest.approx(required_top_qty * sub_assy_per_top) # Total needed before stock

    assert encountered == {top_assembly_id, sub_assembly_id, base_component_id}
