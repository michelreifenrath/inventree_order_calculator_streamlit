# Plan: Handling Part Variants in Stock Calculation

This plan outlines the necessary changes to `inventree_logic.py` to correctly account for InvenTree part variants and the `allow_variants` flag on BOM items when calculating required parts.

## Confirmed API Fields

Based on inspection of the live InvenTree instance:

*   **Part Details (`get_part_details`, `get_final_part_data`):**
    *   `is_template` (boolean): Indicates if the part is a template.
    *   `in_stock` (float): Stock quantity of the part itself (template or regular).
    *   `variant_stock` (float): Combined stock quantity of all variants *under* a template part. (Seems `total_in_stock` might also represent `in_stock + variant_stock`).
*   **BOM Item Details (`get_part_bom`):**
    *   `allow_variants` (boolean): Indicates if variants of the `sub_part` are allowed to fulfill this specific BOM line requirement.

## Implementation Steps

1.  **Modify BOM Traversal (`get_recursive_bom`):**
    *   When processing a `BomItem` (`item`):
        *   Fetch the `sub_part` details (including `is_template`) using `get_part_details(api, item.sub_part)`.
        *   Check if `sub_part_details['is_template']` is `True`.
        *   Retrieve the `allow_variants` flag from the BOM item data: `allow_variants = item._data.get('allow_variants', True)` (Default to True if missing).
        *   **Decision:**
            *   If `is_template` is `True` AND `allow_variants` is `False`:
                *   Add `item.sub_part` to `required_base_components[root_input_id]`.
                *   **Crucially, associate a flag/marker (e.g., in a separate dictionary `template_only_flags[item.sub_part] = True`) indicating that for *at least one* requirement path, only the template's stock should be considered.**
            *   Else (if `sub_part` is not a template, or it is a template and `allow_variants` is `True`):
                *   If `sub_part_details['assembly']` is `True`, recurse: `get_recursive_bom(...)`.
                *   If `sub_part_details['assembly']` is `False`, add to requirements normally: `required_base_components[root_input_id][item.sub_part] += total_sub_quantity`.

2.  **Modify Data Fetching (`get_final_part_data`):**
    *   Ensure the `Part.list` call fetches `is_template`, `in_stock`, and `variant_stock` fields.
    *   Store these values in the returned `final_part_data` dictionary for each part ID.

3.  **Update Calculation Logic (`calculate_required_parts`):**
    *   Before the loop calculating `global_to_order` (around line 341), determine the "template only" status for each unique part ID based on the flags set during BOM traversal.
    *   Inside the loop for each `part_id`:
        *   Retrieve `is_template`, `in_stock`, `variant_stock` from `final_part_data`.
        *   Check if `part_id` has the "template\_only\_stock" flag set.
        *   **Calculate `total_available_stock`:**
            *   If "template\_only\_stock" flag is `True`: `total_available_stock = in_stock`.
            *   Else if `is_template` is `True`: `total_available_stock = in_stock + variant_stock`.
            *   Else (`is_template` is `False`): `total_available_stock = in_stock`.
        *   Calculate `global_to_order = total_required - total_available_stock`.
        *   Use this `global_to_order` when building the final list.

4.  **Testing (`tests/test_inventree_logic.py`):**
    *   Add/update unit tests covering:
        *   Template part required, `allow_variants=False` -> only template stock used.
        *   Template part required, `allow_variants=True` -> template + variant stock used.
        *   Non-template part required.
    *   Mock API responses for `Part.list` and `Part.getBomItems` to include the necessary fields (`is_template`, `in_stock`, `variant_stock`, `allow_variants`).

## Logic Flow Diagram

```mermaid
graph TD
    A[Start Calculation] --> B{Get Required Base Components (Recursive)};
    B --> C{Fetch Final Part Data (incl. is_template, in_stock, variant_stock)};
    C --> D{For each Base Component ID};
    D --> E{Retrieve part data (is_template, in_stock, variant_stock)};
    E --> F{Was this part marked 'template_only_stock' during BOM traversal?};
    F -- Yes --> G[Available Stock = in_stock];
    F -- No --> H{Is Part Template?};
    H -- Yes --> I[Available Stock = in_stock + variant_stock];
    H -- No --> J[Available Stock = in_stock];
    G --> K[Calculate Needed = Required - Available Stock];
    I --> K;
    J --> K;
    K --> L{Needed > 0?};
    L -- Yes --> M[Add to Order List];
    L -- No --> N[Skip Part];
    M --> O{Next Base Component};
    N --> O;
    D -- Loop Next --> D;
    O -- Loop Done --> P[Return Final Order List];

    subgraph "BOM Traversal (get_recursive_bom)"
        direction TB
        bom1[Input: Assembly ID, Qty] --> bom2{Get BOM Items};
        bom2 --> bom3{For each BomItem};
        bom3 --> bom4{Get SubPart Details (is_template)};
        bom4 --> bom5{Get BomItem 'allow_variants' flag};
        bom5 --> bom6{Is SubPart Template AND AllowVariants=False?};
        bom6 -- Yes --> bom7[Add SubPart ID to requirements + Set 'template_only_stock' flag for SubPart ID];
        bom6 -- No --> bom8{Is SubPart Assembly?};
        bom8 -- Yes --> bom9[Recurse get_recursive_bom];
        bom8 -- No --> bom10[Add SubPart ID to requirements (normal)];
        bom7 --> bom11{Next BomItem};
        bom9 --> bom11;
        bom10 --> bom11;
        bom3 -- Loop Next --> bom3;
        bom11 -- Loop Done --> bom12[End Recursion Level];
    end

    B --> bom1;