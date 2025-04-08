# Feature Plan: Replace Part ID Input with Category Dropdown

**Goal:** Replace the manual Part ID input in `app.py` with a dropdown list populated by parts from InvenTree Category 191. The dropdown will show part names, and the selection will drive the BOM calculation.

**Method:** Use the `inventree` Python library directly via `Part.list()`.

**Include:** All parts from Category 191 (not just assemblies).

## Steps

1.  **Update `TASK.md`**: Add this new feature request.
2.  **Enhance `inventree_logic.py`**:
    *   Create `get_parts_in_category(api: InvenTreeAPI, category_id: int) -> list[dict] | None`.
    *   Use `Part.list(api, category=category_id, fields=['pk', 'name'])`.
    *   Add Streamlit caching (`@cache_data`).
    *   Implement error handling.
3.  **Modify `app.py`**:
    *   Define `TARGET_CATEGORY_ID = 191`.
    *   Fetch parts using the new function.
    *   Create `part_name_to_id` mapping.
    *   Replace ID `st.number_input` with `st.selectbox` using part names.
    *   Update session state with the selected part's ID based on the name.
    *   Adjust `add_assembly_input` to set a default selection.
4.  **Testing**: Manual UI testing and unit tests for `get_parts_in_category` (mocking `Part.list`).
5.  **Documentation**: Update `README.md` to describe the new selection method.

## Workflow Diagram

```mermaid
graph TD
    A[Start App] --> B(Define TARGET_CATEGORY_ID=191);
    B --> C{Connect to InvenTree API};
    C --> D[Call inventree_logic.get_parts_in_category(191)];
    D -- List[Part(pk, name)] --> E{Create part_name_to_id Map};
    E --> F{Display Sidebar UI};
    F -- Add Row --> G[Append new entry(default_id, 1.0) to session_state.target_assemblies];
    F -- Remove Row --> H[Pop entry from session_state.target_assemblies];
    F --> I[For each entry in session_state.target_assemblies];
    I -- Stored ID --> J[Find index in Part Names list];
    I --> K[Display Dropdown (Part Names) with index=J];
    I --> L[Display Quantity Input];
    K -- User Selects Name --> M[Get ID from part_name_to_id Map];
    M --> N[Update Part ID in session_state];
    L -- User Enters Quantity --> O[Update Quantity in session_state];
    F --> P[Display 'Calculate' Button];
    P -- User Clicks Calculate --> Q{Prepare target_assemblies dict (ID: Quantity from session_state)};
    Q --> R[Call inventree_logic.calculate_required_parts];
    R --> S{Display Results};
    S --> T[Display 'Reset' Button];
    T -- User Clicks Reset --> U[Clear session_state.results];

    subgraph inventree_logic.py
        direction LR
        logic_get_parts_cat[get_parts_in_category] --> api_part_list(inventree API: Part.list(category=191, fields=['pk','name']));
        logic_calc[calculate_required_parts] --> logic_get_bom(get_recursive_bom);
        logic_get_bom --> logic_get_details(get_part_details);
        logic_get_bom --> logic_get_bom_items(get_bom_items);
        logic_calc --> logic_get_final(get_final_part_data);
    end

    D --> logic_get_parts_cat;
    R --> logic_calc;