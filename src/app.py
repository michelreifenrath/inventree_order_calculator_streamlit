# app.py
import streamlit as st
import pandas as pd
from collections import defaultdict

# import itertools # No longer needed for groupby
import logging
import os  # Import os module
from dotenv import load_dotenv  # Import load_dotenv

# --- Streamlit App Konfiguration ---
st.set_page_config(page_title="InvenTree Order Calculator", layout="wide")
# Importiere die refaktorierte Logik und UI Elemente
from inventree_logic import ( # Relative import
    calculate_required_parts,
    # Functions needed for cache clearing are now in helpers, but might be needed if called directly elsewhere
    # If not called directly, they can be removed from here. Assuming they might be needed for reset.
    # get_part_details,
    # get_bom_items,
    # get_final_part_data
)
from inventree_api_helpers import ( # Relative import
    connect_to_inventree,  # Import from new location
    get_parts_in_category,  # Import from new location
    get_part_details,  # Needed for cache clearing
    get_bom_items,  # Needed for cache clearing
    get_final_part_data,  # Needed for cache clearing
)
from streamlit_ui_elements import ( # Relative import
    render_assembly_inputs,
    render_results_table,
    render_sub_assemblies_table,
)  # Import UI functions
from database_helpers import init_db
from streamlit_ui_elements import render_save_load_controls

st.title("📊 InvenTree Order Calculator")
# --- Inject Custom CSS ---
st.markdown(
    """
    <style>
section[data-testid="stSidebar"][aria-expanded="true"] {
        max-width: 50% !important; /* Apply max-width only when expanded */
    }
    /* Add other custom CSS rules below if needed */
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialisiere die Datenbank
init_db()

# --- Konstanten ---
TARGET_CATEGORY_ID = 191  # ID der Zielkategorie für die Teileauswahl

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
        st.error(
            f"💥 Fehler beim Laden der Teile aus Kategorie {TARGET_CATEGORY_ID}. API-Problem?"
        )
        st.stop()
    elif not category_parts:
        st.warning(f"⚠️ Keine Teile in Kategorie {TARGET_CATEGORY_ID} gefunden.")
        # App kann weiterlaufen, aber die Auswahl wird leer sein.
    else:
        part_name_to_id = {part["name"]: part["pk"] for part in category_parts}
        part_id_to_name = {part["pk"]: part["name"] for part in category_parts}
        part_names = list(part_name_to_id.keys())  # Already sorted by logic function
        default_part_id = category_parts[0]["pk"]  # Use the first part as default
        log.info(
            f"Successfully loaded {len(part_names)} parts from category {TARGET_CATEGORY_ID}."
        )

# --- Initialisierung des Session State für Eingaben ---
# Wird verwendet, um Benutzereingaben über Re-Runs hinweg zu speichern
# Initialisiere Session State nur, wenn er leer ist ODER wenn keine Teile geladen werden konnten (um Fehler zu vermeiden)
if "target_assemblies" not in st.session_state:
    if default_part_id:
        # Initialisiere mit dem ersten Teil aus der Kategorie als Standard
        st.session_state.target_assemblies = [
            {"id": default_part_id, "quantity": 1}
        ]  # Use integer for default quantity
    else:
        # Fallback, wenn keine Teile geladen wurden
        st.session_state.target_assemblies = []

if "results" not in st.session_state:
    st.session_state.results = None  # Hier speichern wir die Berechnungsergebnisse

if "sub_assemblies" not in st.session_state:
    st.session_state.sub_assemblies = None  # Hier speichern wir die Unterbaugruppen

# --- Render UI für Eingaben (Target Assemblies) using the imported function ---
render_assembly_inputs(
    part_names=part_names,
    part_name_to_id=part_name_to_id,
    part_id_to_name=part_id_to_name,
    default_part_id=default_part_id,
    target_category_id=TARGET_CATEGORY_ID,
)

# Füge die Speicher/Laden Kontrollen hinzu
render_save_load_controls()

# --- Berechnungs- und Reset-Buttons ---
st.header("⚙️ Berechnung & Filter")


# Funktion zum Zurücksetzen der Ergebnisse
def reset_calculation() -> None:
    """Clears the calculation results stored in the session state."""
    st.session_state.results = None
    st.session_state.sub_assemblies = None
    # Clear relevant caches
    try:
        # Clear caches from the correct module
        from inventree_api_helpers import ( # Relative import
            get_part_details,
            get_bom_items,
            get_final_part_data,
            get_parts_in_category,
        )

        get_part_details.clear()
        get_bom_items.clear()
        get_final_part_data.clear()
        # Optional: Clear category cache too?
        # get_parts_in_category.clear()
        # Optional: Clear category cache too?
        # get_parts_in_category.clear() # Already cleared above if uncommented
        st.info(
            "Berechnung zurückgesetzt und Cache für Teile-/BOM-Daten gelöscht. Die nächste Berechnung holt frische Daten."
        )
    except Exception as e:
        st.warning(
            f"Ergebnisse zurückgesetzt, aber Fehler beim Löschen des Caches: {e}"
        )


# --- Filter Options ---
# Define the supplier and manufacturer to exclude
SUPPLIER_TO_EXCLUDE = "HAIP Solutions GmbH"  # Corrected to supplier name
# Add a manufacturer to exclude if needed, otherwise leave as None or empty string
MANUFACTURER_TO_EXCLUDE = ""  # Example: "Example Manufacturer Inc."

# Add checkbox for supplier exclusion
exclude_supplier = st.checkbox(
    f"Teile von '{SUPPLIER_TO_EXCLUDE}' ausschließen",
    value=True,
    key="exclude_supplier_checkbox",
)  # Default to True as requested

# Add checkbox for manufacturer exclusion (only if a name is defined)
exclude_manufacturer = False
if MANUFACTURER_TO_EXCLUDE:
    exclude_manufacturer = st.checkbox(
        f"Teile von Hersteller '{MANUFACTURER_TO_EXCLUDE}' ausschließen",
        value=False,
        key="exclude_manufacturer_checkbox",
    )


# --- Calculation and Reset Buttons ---
# Buttons in Spalten anordnen
col_calc, col_reset = st.columns(2)

with col_calc:
    calculate_pressed = st.button(
        " Teilebedarf berechnen", type="primary", use_container_width=True
    )

with col_reset:
    st.button(
        "🔄 Berechnung zurücksetzen",
        on_click=reset_calculation,
        use_container_width=True,
    )


# --- Logik-Aufruf (nur wenn Berechnen geklickt wurde) ---
if calculate_pressed:
    # Bereite das Dictionary für die Logik-Funktion vor
    # Reason: Filter out invalid entries (ID or quantity <= 0) before passing to the calculation logic.
    targets_dict = {
        int(a["id"]): float(
            a["quantity"]
        )  # Convert back to float for the logic function
        for a in st.session_state.target_assemblies
        if a.get("id")
        and int(a["id"]) > 0
        and a.get("quantity")
        and int(a["quantity"]) > 0  # Check integer quantity > 0
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
            # Determine the supplier and manufacturer names to exclude based on checkbox states
            supplier_to_exclude_arg = SUPPLIER_TO_EXCLUDE if exclude_supplier else None
            manufacturer_to_exclude_arg = (
                MANUFACTURER_TO_EXCLUDE if exclude_manufacturer else None
            )

            # Call the core logic with exclusion parameters
            parts_to_order, sub_assemblies = calculate_required_parts(
                api,
                targets_dict,
                exclude_supplier_name=supplier_to_exclude_arg,  # Pass supplier exclusion
                exclude_manufacturer_name=manufacturer_to_exclude_arg,  # Pass manufacturer exclusion
                progress_callback=update_progress,
            )
            # Correct indentation for this block
            st.session_state.results = parts_to_order  # Speichere Ergebnisse im Session State
            st.session_state.sub_assemblies = sub_assemblies  # Speichere Unterbaugruppen im Session State
            # Count how many sub-assemblies need to be built
            sub_assemblies_to_build = sum(1 for item in sub_assemblies if item.get("to_build", 0) > 0)

            if not parts_to_order and sub_assemblies_to_build == 0:
                st.success("✅ Alle benötigten Komponenten und Unterbaugruppen sind ausreichend auf Lager.")
            elif not parts_to_order:
                st.success(
                    f"✅ Berechnung abgeschlossen. Alle Komponenten sind auf Lager, aber {sub_assemblies_to_build} Unterbaugruppen müssen gebaut werden."
                )
            elif sub_assemblies_to_build == 0:
                st.success(
                    f"✅ Berechnung abgeschlossen. {len(parts_to_order)} Teile müssen bestellt werden. Alle benötigten Unterbaugruppen sind auf Lager."
                )
            else:
                st.success(
                    f"✅ Berechnung abgeschlossen. {len(parts_to_order)} Teile müssen bestellt werden und {sub_assemblies_to_build} Unterbaugruppen müssen gebaut werden."
                )

        except Exception as e:
            # Correct indentation for this block
            st.error(f"Ein Fehler ist während der Berechnung aufgetreten: {e}")
            log.error(
                "Fehler während calculate_required_parts in Streamlit App:",
                exc_info=True,
            )
            st.session_state.results = None  # Setze Ergebnisse bei Fehler zurück
            st.session_state.sub_assemblies = None  # Setze Unterbaugruppen bei Fehler zurück


# --- Ergebnisse anzeigen ---
# Call the functions from the UI elements module to render the results
render_results_table(st.session_state.get("results"))

# Render the sub-assemblies table
render_sub_assemblies_table(st.session_state.get("sub_assemblies"))

# Optional: Auto-refresh (siehe IDEA.md für Details zur Implementierung)
# from streamlit_autorefresh import st_autorefresh
# st_autorefresh(interval=300000, limit=None, key="freshening")
