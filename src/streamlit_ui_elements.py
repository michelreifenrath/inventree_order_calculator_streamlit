# streamlit_ui_elements.py
import streamlit as st
import logging
from typing import List, Dict, Optional, Any

log = logging.getLogger(__name__)

# --- UI für Eingaben (Target Assemblies) ---


def add_assembly_input(default_part_id: Optional[int]) -> None:
    """
    Adds a new row for assembly/quantity input using the default part ID
    to the session state 'target_assemblies'.
    """
    if default_part_id:
        if "target_assemblies" not in st.session_state:
            st.session_state.target_assemblies = []  # Initialize if not present
        st.session_state.target_assemblies.append(
            {"id": default_part_id, "quantity": 1}
        )
    else:
        st.warning(
            "Kann keine Zeile hinzufügen, da keine Teile in der Kategorie gefunden wurden."
        )


def remove_assembly_row(index_to_remove: int) -> None:
    """Removes the assembly input row at the specified index from session state."""
    if "target_assemblies" in st.session_state and 0 <= index_to_remove < len(
        st.session_state.target_assemblies
    ):
        del st.session_state.target_assemblies[index_to_remove]
    else:
        log.warning(f"Attempted to remove invalid index: {index_to_remove}")


def render_assembly_inputs(
    part_names: List[str],
    part_name_to_id: Dict[str, int],
    part_id_to_name: Dict[int, str],
    default_part_id: Optional[int],
    target_category_id: int,
) -> None:
    """
    Renders the sidebar UI for defining target assemblies.

    Manages adding/removing rows and updating session state based on user input.
    """
    st.sidebar.header("🎯 Ziel-Assemblies definieren")

    # Button zum Hinzufügen im Sidebar
    st.sidebar.button(
        "➕ Zeile hinzufügen",
        on_click=add_assembly_input,
        args=(default_part_id,),  # Pass default_part_id to the callback
        use_container_width=True,
    )

    # Initialize session state if needed (should ideally be done once in app.py, but check here too)
    if "target_assemblies" not in st.session_state:
        if default_part_id:
            st.session_state.target_assemblies = [
                {"id": default_part_id, "quantity": 1}
            ]
        else:
            st.session_state.target_assemblies = []

    # Zeige Eingabefelder für jede Assembly in der Liste
    if not part_names:
        st.sidebar.warning(
            f"Keine Teile in Kategorie {target_category_id} zum Auswählen verfügbar."
        )
        # Ensure target_assemblies is empty if no parts are available to prevent errors
        if "target_assemblies" in st.session_state:
            st.session_state.target_assemblies = []
    else:
        # Store updates temporarily to apply after rendering all widgets
        updates_to_apply = {}

        # Use a copy for iteration if modifying list length during iteration (though remove_assembly_row modifies state)
        # Iterate directly over indices to safely handle removals via callback
        indices_to_render = list(range(len(st.session_state.target_assemblies)))

        for i in indices_to_render:
            # Check if index is still valid after potential removals from previous iterations
            if i >= len(st.session_state.target_assemblies):
                continue

            assembly_state = st.session_state.target_assemblies[i]

            cols = st.sidebar.columns(
                [0.5, 0.3, 0.2]
            )  # Selectbox, Number Input, Remove Button
            selected_name = None
            new_qty = None

            with cols[0]:
                current_id = assembly_state.get("id")
                current_name = part_id_to_name.get(current_id)
                try:
                    current_index = (
                        part_names.index(current_name)
                        if current_name in part_names
                        else 0
                    )
                except ValueError:
                    current_index = 0
                    # Optionally reset ID if invalid - consider side effects
                    # if default_part_id:
                    #     assembly_state["id"] = default_part_id # Modify state directly here? Risky.

                selected_name = st.selectbox(
                    f"Teil auswählen #{i+1}",
                    options=part_names,
                    index=current_index,
                    key=f"select_{i}",
                    help="Wähle ein Teil aus der InvenTree Kategorie.",
                )

            with cols[1]:
                new_qty = st.number_input(
                    f"Menge #{i+1}",
                    value=int(assembly_state.get("quantity", 1)),
                    key=f"qty_{i}",
                    min_value=1,
                    step=1,
                    format="%d",
                    help="Benötigte Stückzahl (nur ganze Zahlen).",
                )

            with cols[2]:
                st.markdown("<br>", unsafe_allow_html=True)  # Vertical alignment hack
                st.button(
                    "➖",
                    key=f"remove_{i}",
                    on_click=remove_assembly_row,
                    args=(i,),  # Pass current index to remove function
                    help="Diese Zeile entfernen",
                )

            # Prepare updates if widgets rendered successfully
            if selected_name is not None and new_qty is not None:
                new_id = part_name_to_id.get(selected_name, default_part_id)
                updates_to_apply[i] = {"id": new_id, "quantity": int(new_qty)}

        # Apply all collected updates to the session state *after* the loop
        for index, update_data in updates_to_apply.items():
            # Check index validity again before applying update
            if index < len(st.session_state.target_assemblies):
                st.session_state.target_assemblies[index]["id"] = update_data["id"]
                st.session_state.target_assemblies[index]["id"] = update_data["id"]
                st.session_state.target_assemblies[index]["quantity"] = update_data[
                    "quantity"
                ]


# --- Ergebnisse anzeigen ---


def render_results_table(results_list: Optional[List[Dict[str, Any]]]) -> None:
    """
    Renders the results table and CSV download button.

    Args:
        results_list: The list of dictionaries containing parts to order,
                      or None if no calculation has been run or an error occurred.
    """
    import pandas as pd  # Import pandas locally within the function

    st.header("📋 Ergebnisse: Benötigte Teile")

    if results_list is not None:
        if len(results_list) > 0:
            # --- Flat List Display ---
            df_full = pd.DataFrame(results_list)

            # Defensive check: Ensure DataFrame is not empty and has required columns
            # Adjust required_cols based on what calculate_required_parts actually returns
            required_cols = {
                "pk",
                "name",
                "total_required",
                "available_stock",
                "to_order",
                "used_in_assemblies",
                "purchase_orders",
            }
            # Add manufacturer/supplier if they are expected in the final list for display/CSV
            # required_cols.update({"manufacturer_name", "supplier_names"})

            if df_full.empty or not required_cols.issubset(df_full.columns):
                st.error(
                    "Interner Fehler: Berechnungsdaten sind ungültig oder unvollständig."
                )
                log.error(
                    f"Invalid DataFrame created from results_list. Columns: {df_full.columns}. Missing: {required_cols - set(df_full.columns)}"
                )
                # Optionally clear results or stop further processing in the main app
                # st.session_state.results = None # Cannot modify session state here directly
                return  # Stop rendering if data is bad

            # Proceed with DataFrame manipulation only if valid

            # Create a summary string for purchase orders
            df_full["Bestellungen"] = df_full.get("purchase_orders", []).apply(
                lambda po_list: (
                    ", ".join(
                        [
                            f"{po.get('po_ref', '')} ({po.get('quantity', 0)} Stk, Status: {po.get('po_status', '')})"
                            for po in po_list
                        ]
                    )
                    if po_list
                    else "Keine"
                )
            )

            # Create URL column for linking
            # TODO: Make base_url configurable?
            base_url = "https://lager.haip.solutions/"
            df_full["Part URL"] = df_full["pk"].apply(
                lambda pk: f"{base_url}platform/part/{pk}/"
            )

            # Select columns for display (including Name and the hidden URL)
            # Add supplier/manufacturer columns if needed for display
            display_columns_ordered = [
                "name",
                "Part URL",  # Hidden link column
                "total_required",
                "available_stock",
                "to_order",
                "used_in_assemblies",
                "Bestellungen",
                # "manufacturer_name", # Uncomment if needed
                # "supplier_names", # Uncomment if needed (might need formatting)
            ]
            df_display = df_full[
                [col for col in display_columns_ordered if col in df_full.columns]
            ]  # Select only existing columns

            # Update column headers
            df_display.columns = [
                "Name",
                "Part ID",  # Header for the URL column
                "Gesamt benötigt",
                "Verfügbar",
                "Zu bestellen",
                "Verwendet in Assemblies",
                "Bestellungen",
                # "Hersteller", # Uncomment if needed
                # "Lieferanten", # Uncomment if needed
            ]

            # Configure columns for st.data_editor
            column_config = {
                "Name": st.column_config.TextColumn(width="large"),
                "Part ID": st.column_config.LinkColumn(
                    display_text=r"https://lager.haip.solutions/platform/part/(\d+)/",
                    validate=r"^https://lager.haip.solutions/platform/part/\d+/$",
                    help="Klicken, um das Teil in InvenTree zu öffnen",
                    width="small",
                ),
                "Bestellungen": st.column_config.TextColumn(width="large"),
                # Add config for manufacturer/supplier if displayed
                # "Hersteller": st.column_config.TextColumn(width="medium"),
                # "Lieferanten": st.column_config.TextColumn(width="medium"), # Might need custom formatting
            }

            st.data_editor(
                df_display,
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
            )

            # --- CSV Download ---
            # Reorder columns for CSV clarity, include pk and potentially raw supplier/manufacturer
            csv_columns_ordered = [
                "pk",
                "name",
                "total_required",
                "available_stock",
                "to_order",
                "used_in_assemblies",
                "Bestellungen",  # Formatted PO string
                # "manufacturer_name", # Raw manufacturer name
                # "supplier_names", # Raw list of supplier names
            ]
            df_csv = df_full[
                [col for col in csv_columns_ordered if col in df_full.columns]
            ]

            # Use consistent headers, map pk to Part ID
            df_csv.columns = [
                "Part ID",
                "Name",
                "Gesamt benötigt",
                "Verfügbar",
                "Zu bestellen",
                "Verwendet in Assemblies",
                "Bestellungen",
                # "Hersteller",
                # "Lieferanten (Liste)", # Indicate it's a list
            ]

            try:
                csv_data = df_csv.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="💾 Ergebnisse als CSV herunterladen",
                    data=csv_data,
                    file_name="inventree_order_list.csv",
                    mime="text/csv",
                )
            except Exception as e:
                st.error(f"Fehler beim Erstellen der CSV-Datei: {e}")
                log.error("Error generating CSV data", exc_info=True)

        elif results_list is not None and len(results_list) == 0:
            # Handle case where calculation succeeded but yielded an empty list
            st.info(
                "👍 Alle Teile auf Lager oder Filterkriterien erfüllen keine Teile."
            )
    else:
        # No results calculated yet
        st.info("Klicke auf 'Teilebedarf berechnen', um die Ergebnisse anzuzeigen.")
