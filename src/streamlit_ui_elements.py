# streamlit_ui_elements.py
import streamlit as st
import logging
from typing import List, Dict, Optional, Any
from database_helpers import (
    save_current_assemblies,
    load_saved_assemblies,
    get_saved_assembly_names,
    delete_saved_assembly
)

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


def render_results_table(results_list: Optional[List[Dict[str, Any]]], link_style: str = "New GUI (/platform/..)") -> None:
    """
    Renders the results table and CSV download button.

    Args:
        results_list: The list of dictionaries containing parts to order,
                      or None if no calculation has been run or an error occurred.
    """
    render_parts_to_order_table(results_list, link_style=link_style)


def render_sub_assemblies_table(
    sub_assemblies_list: Optional[List[Dict[str, Any]]],
    link_style: str = "New GUI (/platform/..)", # Added link_style argument
) -> None:
    """
    Renders a table showing required sub-assemblies.

    Args:
        sub_assemblies_list: The list of dictionaries containing sub-assemblies to build,
                            or None if no calculation has been run or an error occurred.
    """
    import pandas as pd  # Import pandas locally within the function

    st.header("🔧 Benötigte Unterbaugruppen")

    if sub_assemblies_list is not None:
        if len(sub_assemblies_list) > 0:
            # Create DataFrame from sub-assemblies list
            df_full = pd.DataFrame(sub_assemblies_list)

            # Defensive check: Ensure DataFrame is not empty and has required columns
            # Ensure 'verfuegbar' is present, remove 'required_for_order'
            required_cols = {"pk", "name", "quantity", "available_stock", "verfuegbar", "to_build", "for_assembly"}

            if df_full.empty or not required_cols.issubset(df_full.columns):
                st.error(
                    "Interner Fehler: Daten für Unterbaugruppen sind ungültig oder unvollständig."
                )
                log.error(
                    f"Invalid DataFrame created from sub_assemblies_list. Columns: {df_full.columns}. Missing: {required_cols - set(df_full.columns)}"
                )
                return  # Stop rendering if data is bad

            # Determine URL prefix based on link style
            base_url = "https://lager.haip.solutions" # Remove trailing slash
            url_prefix = "/platform/part" if "New GUI" in link_style else "/part"

            # Create URL column for linking
            df_full["Part URL"] = df_full["pk"].apply(
                lambda pk: f"{base_url}{url_prefix}/{pk}/" # Use url_prefix
            )

            # Select columns for display
            # Replace 'required_for_order' with 'verfuegbar' after 'available_stock'
            display_columns_ordered = [
                "name",
                "Part URL",  # Hidden link column
                "quantity",
                "available_stock",
                "verfuegbar", # New column
                "to_build",
                "for_assembly",
            ]
            df_display = df_full[
                [col for col in display_columns_ordered if col in df_full.columns]
            ]

            # Update column headers
            # Replace 'Benötigt (Bestellung)' with 'Verfügbar'
            df_display.columns = [
                "Name",
                "Part ID",  # Header for the URL column
                "Benötigt (Gesamt)", # Renamed for clarity
                "Auf Lager",
                "Verfügbar", # New header
                "Zu bauen",
                "Für Assembly",
            ]

            # Determine display regex based on link style
            base_url_display = "https://lager.haip.solutions" # For display regex
            url_prefix_display = "/platform/part" if "New GUI" in link_style else "/part"
            display_regex = rf"^{base_url_display}{url_prefix_display}/(\d+)/$" # Use url_prefix_display

            # Configure columns for st.data_editor
            column_config = {
                "Name": st.column_config.TextColumn(width="large"),
                "Part ID": st.column_config.LinkColumn(
                    # display_text=r"https://lager.haip.solutions/platform/part/(\d+)/", # Old static regex
                    display_text=display_regex, # Use dynamic regex
                    # validate=r"^https://lager.haip.solutions/platform/part/\d+/$", # Validate might need adjustment too if base_url changes
                    validate=display_regex, # Use the same regex for validation for now
                    help="Klicken, um die Unterbaugruppe in InvenTree zu öffnen",
                    width="small",
                ),
                "Benötigt (Gesamt)": st.column_config.NumberColumn(format="%.2f", width="small", help="Gesamt benötigte Menge für alle Ziel-Assemblies."),
                "Auf Lager": st.column_config.NumberColumn(format="%.2f", width="small"),
                "Verfügbar": st.column_config.NumberColumn(format="%.2f", width="small", help="Verfügbarer Bestand nach Abzug des Gesamtbedarfs (kann negativ sein)."), # New config
                "Zu bauen": st.column_config.NumberColumn(format="%.2f", width="small", help="Anzahl, die gebaut werden muss (Benötigt (Gesamt) - Auf Lager)"), # Updated help text
                "Für Assembly": st.column_config.TextColumn(width="large"),
            }

            st.data_editor(
                df_display,
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
            )

            # CSV Download
            # Replace 'required_for_order' with 'verfuegbar'
            csv_columns_ordered = [
                "pk",
                "name",
                "quantity",
                "available_stock",
                "verfuegbar", # New column
                "to_build",
                "for_assembly",
                "for_assembly_id",
            ]
            df_csv = df_full[
                [col for col in csv_columns_ordered if col in df_full.columns]
            ]

            # Use consistent headers
            # Replace 'Benötigt (Bestellung)' with 'Verfügbar'
            df_csv.columns = [
                "Part ID",
                "Name",
                "Benötigt (Gesamt)", # Renamed for clarity
                "Auf Lager",
                "Verfügbar", # New header
                "Zu bauen",
                "Für Assembly",
                "Assembly ID",
            ]

            try:
                csv_data = df_csv.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="💾 Unterbaugruppen als CSV herunterladen",
                    data=csv_data,
                    file_name="inventree_sub_assemblies.csv",
                    mime="text/csv",
                )
            except Exception as e:
                st.error(f"Fehler beim Erstellen der CSV-Datei: {e}")
                log.error("Error generating CSV data for sub-assemblies", exc_info=True)

        else:
            # Handle case where calculation succeeded but yielded an empty list
            st.info(
                "👍 Keine Unterbaugruppen benötigt."
            )
    else:
        # No results calculated yet
        st.info("Klicke auf 'Teilebedarf berechnen', um die Ergebnisse anzuzeigen.")


def render_parts_to_order_table(
    results_list: Optional[List[Dict[str, Any]]],
    link_style: str = "New GUI (/platform/..)", # Added link_style argument
) -> None:
    """
    Renders the table of parts to order and CSV download button.

    Args:
        results_list: The list of dictionaries containing parts to order,
                      or None if no calculation has been run or an error occurred.
    """
    import pandas as pd  # Import pandas locally within the function

    st.header("📋 Ergebnisse: Benötigte Teile")

    # Checkboxes for filtering display
    col1, col2 = st.columns(2) # Adjusted for two checkboxes
    with col1:
        # --- Display Filter: BOM Consumables ---
        hide_bom_consumables = st.checkbox(
            "BOM-Verbrauchsmaterial ausblenden",
            value=st.session_state.get("hide_bom_consumables_checkbox", False), # Persist state
            key="hide_bom_consumables_checkbox",
            help="Blendet Teile aus der Anzeige aus, die auf einer Stückliste als Verbrauchsmaterial gekennzeichnet sind."
        )
    with col2:
        # --- Display & Calculation Filter: HAIP Solutions ---
        # This single checkbox controls both calculation exclusion (handled in app.py)
        # and display filtering (handled below).
        exclude_haip_supplier = st.checkbox(
            "HAIP Solutions Teile ausschließen", # Clearer label
            value=st.session_state.get("exclude_haip_supplier_checkbox", True), # Default to True, persist state
            key="exclude_haip_supplier_checkbox",
            help="Blendet Teile von 'HAIP Solutions GmbH' nur in dieser Tabelle aus. Die Berechnung bleibt unberührt."
        )


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
                "is_bom_consumable", # Ensure the flag is expected
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

            # --- Filter based on checkboxes ---
            df_processed = df_full.copy() # Start with the full data

            # Filter BOM Consumables
            if hide_bom_consumables:
                if 'is_bom_consumable' in df_processed.columns:
                    df_processed = df_processed[df_processed['is_bom_consumable'] == False]
                else:
                    st.warning("Spalte 'is_bom_consumable' nicht in den Daten gefunden. Filter kann nicht angewendet werden.")
                    log.warning("Column 'is_bom_consumable' not found in DataFrame. Skipping BOM consumable filter.")

            # Filter HAIP Parts (Display Only) - Based on the new single checkbox and actual supplier data
            if exclude_haip_supplier:
                # Define the supplier name to check against (should match app.py's SUPPLIER_TO_EXCLUDE)
                supplier_to_exclude_display = "HAIP Solutions GmbH"

                # Check if 'supplier_parts' column exists and is iterable
                if 'supplier_parts' in df_processed.columns:
                    # Function to check if any supplier in the list matches the excluded supplier
                    # Make function slightly more robust
                    def has_excluded_supplier(supplier_list):
                        if not isinstance(supplier_list, list):
                            return False # Not a list, cannot contain the supplier
                        return any(
                            isinstance(sp, dict) and sp.get("supplier_name") == supplier_to_exclude_display
                            for sp in supplier_list
                        )

                    # Apply the filter: Keep rows that DO NOT have the excluded supplier
                    df_processed = df_processed[~df_processed['supplier_parts'].apply(has_excluded_supplier)]
                else:
                    st.warning("Spalte 'supplier_parts' nicht in den Daten gefunden. HAIP-Teile-Anzeigefilter kann nicht angewendet werden.")
                    log.warning("Column 'supplier_parts' not found in DataFrame. Skipping HAIP parts display filter.")


            # --- IMPORTANT: Use df_processed for all subsequent operations ---

            # Check if the filtered DataFrame is empty before proceeding
            if df_processed.empty:
                 st.info(
                     "Keine Teile zum Anzeigen nach Anwendung der Filter." if hide_bom_consumables else "Es gibt keine Teile anzuzeigen."
                 )
                 # Optionally return or skip further processing like CSV download
                 # return # Or just skip the data_editor and download button parts
            else:
                # Create a summary string for purchase orders using the processed DataFrame
                df_processed["Bestellungen"] = df_processed.get("purchase_orders", []).apply(
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

                # Determine URL prefix based on link style
                base_url = "https://lager.haip.solutions" # Remove trailing slash
                url_prefix = "/platform/part" if "New GUI" in link_style else "/part"

                # Create URL column for linking using df_processed
                df_processed["Part URL"] = df_processed["pk"].apply(
                    lambda pk: f"{base_url}{url_prefix}/{pk}/" # Use url_prefix
                )

                # Select columns for display (including Name and the hidden URL)
                # Add supplier/manufacturer columns if needed for display
                display_columns_ordered = [
                    "name",
                    "Part URL",  # Hidden link column
                    "total_required",
                    "available_stock",
                    "saldo", # Added Saldo
                    "to_order",
                    "used_in_assemblies",
                    "Bestellungen",
                    # "manufacturer_name", # Uncomment if needed
                    # "supplier_names", # Uncomment if needed (might need formatting)
                    # "is_bom_consumable", # Optionally display the flag for debugging/info
                ]
                # Use df_processed
                df_display = df_processed[
                    [col for col in display_columns_ordered if col in df_processed.columns]
                ]  # Select only existing columns

                # Update column headers
                df_display.columns = [
                    "Name",
                    "Part ID",  # Header for the URL column
                    "Gesamt benötigt",
                    "Auf Lager",
                    "Verfügbar", # Renamed from Saldo
                    "Zu bestellen",
                    "Verwendet in Assemblies",
                    "Bestellungen",
                    # "Hersteller", # Uncomment if needed
                    # "Lieferanten", # Uncomment if needed
                    # "BOM Konsum?", # Optional header for the flag
                ]

                # Determine display regex based on link style
                base_url_display = "https://lager.haip.solutions" # For display regex
                url_prefix_display = "/platform/part" if "New GUI" in link_style else "/part"
                display_regex = rf"^{base_url_display}{url_prefix_display}/(\d+)/$" # Use url_prefix_display

                # Configure columns for st.data_editor
                column_config = {
                    "Name": st.column_config.TextColumn(width="large"),
                    "Part ID": st.column_config.LinkColumn(
                        # display_text=r"https://lager.haip.solutions/platform/part/(\d+)/", # Old static regex
                        display_text=display_regex, # Use dynamic regex
                        # validate=r"^https://lager.haip.solutions/platform/part/\d+/$", # Validate might need adjustment too if base_url changes
                        validate=display_regex, # Use the same regex for validation for now
                        help="Klicken, um das Teil in InvenTree zu öffnen",
                        width="small",
                    ),
                    "Verfügbar": st.column_config.NumberColumn(
                        format="%d",
                        width="small",
                        help="Verfügbarer Lagerbestand minus Gesamtbedarf (kann negativ sein)."
                    ),
                    "Bestellungen": st.column_config.TextColumn(width="large"),
                    # Add config for manufacturer/supplier if displayed
                    # "Hersteller": st.column_config.TextColumn(width="medium"),
                    # "Lieferanten": st.column_config.TextColumn(width="medium"), # Might need custom formatting
                    # "BOM Konsum?": st.column_config.CheckboxColumn(width="small"), # Optional display config
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
                    "saldo", # Added Saldo
                    "to_order",
                    "used_in_assemblies",
                    "Bestellungen",  # Formatted PO string
                    "is_bom_consumable", # Include the flag in CSV
                    # "manufacturer_name", # Raw manufacturer name
                    # "supplier_names", # Raw list of supplier names
                ]
                # Use df_processed
                df_csv = df_processed[
                    [col for col in csv_columns_ordered if col in df_processed.columns]
                ]

                # Use consistent headers, map pk to Part ID
                df_csv.columns = [
                    "Part ID",
                    "Name",
                    "Gesamt benötigt",
                    "Auf Lager",
                    "Saldo", # Added Saldo header
                    "Zu bestellen",
                    "Verwendet in Assemblies",
                    "Bestellungen",
                    "Ist BOM Verbrauchsmaterial", # CSV Header for the flag
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
                "👍 Alle Teile auf Lager oder keine Teile entsprechen den Kriterien." # Adjusted message
            )
    else:
        # No results calculated yet
        st.info("Klicke auf 'Teilebedarf berechnen', um die Ergebnisse anzuzeigen.")


def render_save_load_controls() -> None:
    """Render UI controls for saving and loading assembly selections."""
    st.sidebar.header("💾 Baugruppen speichern/laden")
    
    # Save current selection
    with st.sidebar.expander("Aktuelle Auswahl speichern", expanded=False):
        save_name = st.text_input(
            "Name für aktuelle Auswahl:",
            key="save_name",
            placeholder="z.B. Projekt A"
        )
        if st.button("Speichern", use_container_width=True, key="save_button"):
            if save_name:
                if save_current_assemblies(save_name):
                    st.success(f"Baugruppen-Auswahl '{save_name}' erfolgreich gespeichert!")
            else:
                st.warning("Bitte einen Namen eingeben!")
    
    # Load saved selection
    saved_names = get_saved_assembly_names()
    if saved_names:
        with st.sidebar.expander("Gespeicherte Auswahl laden", expanded=False):
            selected_save = st.selectbox(
                "Gespeicherte Konfiguration:",
                options=saved_names,
                key="load_selection"
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Laden", use_container_width=True):
                    if load_saved_assemblies(selected_save):
                        st.success(f"Baugruppen-Auswahl '{selected_save}' geladen!")
                        st.rerun()  # Füge rerun() direkt nach dem erfolgreichen Laden hinzu
            with col2:
                if st.button("Löschen", use_container_width=True):
                    if delete_saved_assembly(selected_save):
                        st.success(f"Konfiguration '{selected_save}' gelöscht!")
                        st.rerun()
    else:
        st.sidebar.info("Keine gespeicherten Konfigurationen vorhanden.")
