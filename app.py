# app.py
import streamlit as st
import pandas as pd
from collections import defaultdict
# import itertools # No longer needed for groupby
import logging
import os  # Import os module
from dotenv import load_dotenv  # Import load_dotenv

# Importiere die refaktorierte Logik
from inventree_logic import (
    connect_to_inventree,
    calculate_required_parts,
    get_parts_in_category, # Import the new function
    # Import functions whose cache needs clearing
    get_part_details,
    get_bom_items,
    get_final_part_data,
)

# --- Streamlit App Konfiguration ---
st.set_page_config(page_title="InvenTree Order Calculator", layout="wide")
st.title("📊 InvenTree Order Calculator")

# --- Konstanten ---
TARGET_CATEGORY_ID = 191 # ID der Zielkategorie für die Teileauswahl

# Konfiguriere Logging (optional, um Logs in der Konsole zu sehen)
# Streamlit kann Logs nicht direkt in der UI anzeigen, außer man fängt sie speziell ab.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# --- Lade Umgebungsvariablen aus .env Datei ---
# Explicitly find and load .env file
from dotenv import find_dotenv

dotenv_path = find_dotenv()
loaded = load_dotenv(
    dotenv_path=dotenv_path, verbose=True
)  # Add verbose=True for debug output
print(f"Attempting to load .env file from: {dotenv_path}")
print(f".env file loaded successfully: {loaded}")


# --- Verbindung zur API (mit Caching aus inventree_logic) ---
inventree_url = os.getenv("INVENTREE_URL")
inventree_token = os.getenv("INVENTREE_TOKEN")

# --- Debugging Print Statements ---
print(f"Read INVENTREE_URL from environment: {inventree_url}")
print(f"Read INVENTREE_TOKEN from environment: {inventree_token}")
# --- End Debugging ---
if not inventree_url or not inventree_token:
    st.error(
        "🚨 Fehler: INVENTREE_URL und/oder INVENTREE_TOKEN nicht in der .env Datei oder Umgebungsvariablen gefunden!"
    )
    st.info(
        'Bitte erstelle eine `.env` Datei im Projektverzeichnis mit deinen Zugangsdaten:\n\nINVENTREE_URL="YOUR_URL"\nINVENTREE_TOKEN="YOUR_TOKEN"'
    )
    st.stop()  # Hält die App-Ausführung an

api = connect_to_inventree(inventree_url, inventree_token)

if api is None:
    st.error(
        "💥 Verbindung zur InvenTree API fehlgeschlagen. Bitte überprüfe URL/Token und Netzwerk."
    )
    st.stop()
else:
    st.success(f"✅ Erfolgreich verbunden mit InvenTree API Version: {api.api_version}")
    
    # --- Teile aus Zielkategorie laden ---
    category_parts = get_parts_in_category(api, TARGET_CATEGORY_ID)
    part_name_to_id = {}
    part_id_to_name = {}
    part_names = []
    default_part_id = None
    
    if category_parts is None:
        st.error(f"💥 Fehler beim Laden der Teile aus Kategorie {TARGET_CATEGORY_ID}. API-Problem?")
        st.stop()
    elif not category_parts:
        st.warning(f"⚠️ Keine Teile in Kategorie {TARGET_CATEGORY_ID} gefunden.")
        # App kann weiterlaufen, aber die Auswahl wird leer sein.
    else:
        part_name_to_id = {part['name']: part['pk'] for part in category_parts}
        part_id_to_name = {part['pk']: part['name'] for part in category_parts}
        part_names = list(part_name_to_id.keys()) # Already sorted by logic function
        default_part_id = category_parts[0]['pk'] # Use the first part as default
        log.info(f"Successfully loaded {len(part_names)} parts from category {TARGET_CATEGORY_ID}.")
    
# --- Initialisierung des Session State für Eingaben ---
# Wird verwendet, um Benutzereingaben über Re-Runs hinweg zu speichern
# Initialisiere Session State nur, wenn er leer ist ODER wenn keine Teile geladen werden konnten (um Fehler zu vermeiden)
if "target_assemblies" not in st.session_state:
    if default_part_id:
         # Initialisiere mit dem ersten Teil aus der Kategorie als Standard
        st.session_state.target_assemblies = [{"id": default_part_id, "quantity": 1}] # Use integer for default quantity
    else:
        # Fallback, wenn keine Teile geladen wurden
        st.session_state.target_assemblies = []

if "results" not in st.session_state:
    st.session_state.results = None  # Hier speichern wir die Berechnungsergebnisse

# --- UI für Eingaben (Target Assemblies) ---
st.sidebar.header("🎯 Ziel-Assemblies definieren")


# Funktion zum Hinzufügen einer neuen Zeile für Assembly-Eingabe
def add_assembly_input() -> None:
    """Adds a new row for assembly/quantity input using the default part ID."""
    if default_part_id:
        st.session_state.target_assemblies.append({"id": default_part_id, "quantity": 1}) # Use integer for added quantity
    else:
        # Verhindere das Hinzufügen, wenn keine Teile zur Auswahl stehen
        st.warning("Kann keine Zeile hinzufügen, da keine Teile in der Kategorie gefunden wurden.")


# Funktion zum Entfernen einer bestimmten Assembly-Zeile
def remove_assembly_row(index_to_remove: int) -> None:
    """Removes the assembly input row at the specified index."""
    if 0 <= index_to_remove < len(st.session_state.target_assemblies):
        del st.session_state.target_assemblies[index_to_remove]
    else:
        log.warning(f"Attempted to remove invalid index: {index_to_remove}")

# Button zum Hinzufügen im Sidebar
st.sidebar.button(
    "➕ Zeile hinzufügen", on_click=add_assembly_input, use_container_width=True
)
# Removed the "Letzte entfernen" button and its column


# Zeige Eingabefelder für jede Assembly in der Liste
if not part_names:
    st.sidebar.warning(f"Keine Teile in Kategorie {TARGET_CATEGORY_ID} zum Auswählen verfügbar.")
else:
    # Store updates temporarily to apply after rendering both widgets in a row
    updates_to_apply = {}

    for i, assembly_state in enumerate(st.session_state.target_assemblies):
        # Add a third column for the remove button
        cols = st.sidebar.columns(
            [0.5, 0.3, 0.2] # Adjust widths: Selectbox, Number Input, Remove Button
            # Removed vertical_alignment
        )
        selected_name = None
        new_qty = None

        with cols[0]:
            # Finde den Index des aktuell gespeicherten Teils für die Vorauswahl
            current_id = assembly_state.get("id") # Use .get for safety
            current_name = part_id_to_name.get(current_id)
            try:
                # Setze Index basierend auf dem Namen, der zur ID gehört
                current_index = part_names.index(current_name) if current_name in part_names else 0
            except ValueError:
                 # Fallback, falls die gespeicherte ID nicht (mehr) in der Liste ist
                current_index = 0
                # Optional: Setze die ID im State auf den Default zurück, wenn sie ungültig wird
                # Note: Doing this here might trigger extra reruns, consider if needed
                # if default_part_id:
                #     st.session_state.target_assemblies[i]["id"] = default_part_id

            # Render selectbox and store the selected name
            selected_name = st.selectbox(
                f"Teil auswählen #{i+1}",
                options=part_names,
                index=current_index,
                key=f"select_{i}", # Keep index-based key
                help="Wähle ein Teil aus der InvenTree Kategorie. Lange Namen werden ggf. gekürzt.", # Add note about truncation
            )

        with cols[1]:
            # Render number input and store the new quantity
            new_qty = st.number_input(
                f"Menge #{i+1}",
                value=int(assembly_state.get("quantity", 1)), # Ensure integer value
                key=f"qty_{i}", # Keep index-based key
                min_value=1, # Minimum quantity is 1
                step=1, # Step by whole numbers
                format="%d", # Display as integer
                help="Benötigte Stückzahl dieses Teils (nur ganze Zahlen).", # Update help text
            )
        with cols[2]: # Indented
             # Add manual vertical space to push button down
             st.markdown("<br>", unsafe_allow_html=True)
             st.button(
                         "➖",
                         key=f"remove_{i}",
                         # Use lambda with default argument to capture index
                         on_click=lambda idx=i: remove_assembly_row(idx),
                         # Removed args=(i,)
                         help="Diese Zeile entfernen"
                     ) # Removed extra st.button(

        # Prepare updates for this index after rendering
        # Prepare updates for this index after rendering (Indented)
        if selected_name is not None and new_qty is not None:
             new_id = part_name_to_id.get(selected_name, default_part_id) # Fallback auf Default ID
             # Ensure quantity is stored as int, but new_qty from number_input might be float if user types decimal point
             updates_to_apply[i] = {"id": new_id, "quantity": int(new_qty)} # Indented inside if


    # Apply all collected updates to the session state *after* the loop
    for index, update_data in updates_to_apply.items():
        if index < len(st.session_state.target_assemblies): # Check index validity
             st.session_state.target_assemblies[index]["id"] = update_data["id"]
             st.session_state.target_assemblies[index]["quantity"] = int(update_data["quantity"]) # Ensure integer in state



# --- Berechnungs- und Reset-Buttons ---
st.header("⚙️ Berechnung steuern")

# Funktion zum Zurücksetzen der Ergebnisse
def reset_calculation() -> None:
    """Clears the calculation results stored in the session state."""
    st.session_state.results = None
    # Clear relevant caches
    try:
        get_part_details.clear()
        get_bom_items.clear()
        get_final_part_data.clear()
        # Optional: Clear category cache too?
        # get_parts_in_category.clear()
        st.info("Berechnung zurückgesetzt und Cache für Teile-/BOM-Daten gelöscht. Die nächste Berechnung holt frische Daten.")
    except Exception as e:
        st.warning(f"Ergebnisse zurückgesetzt, aber Fehler beim Löschen des Caches: {e}")

# Buttons in Spalten anordnen
col_calc, col_reset = st.columns(2)

with col_calc:
    calculate_pressed = st.button(" Teilebedarf berechnen", type="primary", use_container_width=True)

with col_reset:
    st.button("🔄 Berechnung zurücksetzen", on_click=reset_calculation, use_container_width=True)


# --- Logik-Aufruf (nur wenn Berechnen geklickt wurde) ---
if calculate_pressed:
    # Bereite das Dictionary für die Logik-Funktion vor
    # Reason: Filter out invalid entries (ID or quantity <= 0) before passing to the calculation logic.
    targets_dict = {
        int(a["id"]): float(a["quantity"]) # Convert back to float for the logic function
        for a in st.session_state.target_assemblies
        if a.get("id") and int(a["id"]) > 0 and a.get("quantity") and int(a["quantity"]) > 0 # Check integer quantity > 0
    }

    if not targets_dict:
        st.warning(
            "⚠️ Bitte mindestens ein gültiges Teil mit Menge (> 0) auswählen/eingeben."
        )
    else:
        # Define progress bar and callback
        progress_bar = st.progress(0, text="Starting calculation...")
        def update_progress(value, text):
            progress_bar.progress(value, text=text)

        # No longer need spinner, use progress bar context
        # with st.spinner(...):
        try:
            # Rufe die Kernlogik auf, übergib den Callback
            parts_to_order = calculate_required_parts(
                api, targets_dict, progress_callback=update_progress
            )
            # Correct indentation for this block
            st.session_state.results = (
                parts_to_order  # Speichere Ergebnisse im Session State
            )
            if not parts_to_order:
                st.success(
                    "✅ Alle benötigten Komponenten sind ausreichend auf Lager."
                )
            else:
                st.success(
                    f"✅ Berechnung abgeschlossen. {len(parts_to_order)} Teile müssen bestellt werden."
                )

        except Exception as e:
            # Correct indentation for this block
            st.error(f"Ein Fehler ist während der Berechnung aufgetreten: {e}")
            log.error(
                "Fehler während calculate_required_parts in Streamlit App:",
                exc_info=True,
            )
            st.session_state.results = None  # Setze Ergebnisse bei Fehler zurück (Unindented)


# --- Ergebnisse anzeigen ---
st.header("📋 Ergebnisse: Benötigte Teile")

# Color palette no longer needed
# COLOR_PALETTE = [
#     "#E0F2F7", # Light Cyan
#     "#E8F5E9", # Light Green
#     "#FFF9C4", # Light Yellow
#     "#FCE4EC", # Light Pink
# ] # End of commented out palette

if st.session_state.results is not None: # Ensure this is at the correct base indentation level
    results_list = st.session_state.results # This is now the flat list
    if len(results_list) > 0:
        # --- Flat List Display ---
        df_full = pd.DataFrame(results_list)

        # Create a summary string for purchase orders
        df_full["Bestellungen"] = df_full.get("purchase_orders", []).apply(
            # Update f-string to include quantity
            lambda po_list: ", ".join([f"{po.get('ref', '')} ({po.get('quantity', 0)} Stk, Status: {po.get('status', '')})" for po in po_list]) if po_list else "Keine"
        )

        # Select and rename columns for display
        df_display = df_full[[
            "pk",
            "name",
            "total_required", # Use the total required quantity
            "in_stock",
            "to_order", # This is the global amount
            "used_in_assemblies", # Existing column
            "Bestellungen", # New column with PO info
        ]]
        df_display.columns = [
            "Part ID",
            "Name",
            "Gesamt benötigt", # Updated name
            "Auf Lager", # Removed (Global)
            "Zu bestellen", # Removed (Global)
            "Verwendet in Assemblies", # Existing column
            "Bestellungen", # New column name
        ]
        st.data_editor(
            df_display,
            column_config={
                "Name": st.column_config.TextColumn(width="large"),
                "Bestellungen": st.column_config.TextColumn(width="large"),
            },
            use_container_width=True,
            hide_index=True,
            disabled=True
        )

        # --- CSV Download (using the same flat structure) ---
        # df_full is already created above
        # Reorder columns for CSV clarity
        df_csv = df_full[[
            "pk",
            "name",
            "total_required",
            "in_stock",
            "to_order",
            "used_in_assemblies",
            "Bestellungen",
        ]]
        # Use the same column names as the display table for consistency
        df_csv.columns = [
            "Part ID",
            "Name",
            "Gesamt benötigt",
            "Auf Lager", # Removed (Global)
            "Zu bestellen", # Removed (Global)
            "Verwendet in Assemblies",
            "Bestellungen",
        ]
        csv_data = df_csv.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Ergebnisse als CSV herunterladen", # Simpler label now
            data=csv_data,
            file_name="inventree_order_list.csv", # Revert filename
            mime="text/csv",
        )

        # Optional: Markdown-Ausgabe (wie im Original-Skript)
        # Hier könntest du die save_results_to_markdown Funktion importieren und nutzen
        # oder den Markdown-String direkt erstellen und mit st.markdown anzeigen/downloaden.

    elif len(st.session_state.results) == 0 and st.session_state.results is not None:
        # Reason: Explicitly handle the case where calculation succeeded (`results` is not None) but yielded an empty list (no parts to order).
        # This provides clearer feedback in the results section than just relying on the success message after calculation.
        st.info("👍 Alle Teile auf Lager, keine Bestellung notwendig.")
else:
    st.info("Klicke auf 'Teilebedarf berechnen', um die Ergebnisse anzuzeigen.")

# Optional: Auto-refresh (siehe IDEA.md für Details zur Implementierung)
# from streamlit_autorefresh import st_autorefresh
# st_autorefresh(interval=300000, limit=None, key="freshening")
