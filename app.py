# app.py
import streamlit as st
import pandas as pd
from collections import defaultdict
import logging
import os # Import os module
from dotenv import load_dotenv # Import load_dotenv

# Importiere die refaktorierte Logik
from inventree_logic import connect_to_inventree, calculate_required_parts

# --- Streamlit App Konfiguration ---
st.set_page_config(page_title="InvenTree Order Calculator", layout="wide")
st.title("📊 InvenTree Order Calculator")

# Konfiguriere Logging (optional, um Logs in der Konsole zu sehen)
# Streamlit kann Logs nicht direkt in der UI anzeigen, außer man fängt sie speziell ab.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Lade Umgebungsvariablen aus .env Datei ---
load_dotenv()

# --- Verbindung zur API (mit Caching aus inventree_logic) ---
inventree_url = os.getenv("INVENTREE_URL")
inventree_token = os.getenv("INVENTREE_TOKEN")

if not inventree_url or not inventree_token:
    st.error("🚨 Fehler: INVENTREE_URL und/oder INVENTREE_TOKEN nicht in der .env Datei oder Umgebungsvariablen gefunden!")
    st.info("Bitte erstelle eine `.env` Datei im Projektverzeichnis mit deinen Zugangsdaten:\n\nINVENTREE_URL=\"YOUR_URL\"\nINVENTREE_TOKEN=\"YOUR_TOKEN\"")
    st.stop() # Hält die App-Ausführung an

api = connect_to_inventree(inventree_url, inventree_token)

if api is None:
    st.error("💥 Verbindung zur InvenTree API fehlgeschlagen. Bitte überprüfe URL/Token und Netzwerk.")
    st.stop()
else:
    st.success(f"✅ Erfolgreich verbunden mit InvenTree API Version: {api.api_version}")

# --- Initialisierung des Session State für Eingaben ---
# Wird verwendet, um Benutzereingaben über Re-Runs hinweg zu speichern
if 'target_assemblies' not in st.session_state:
    # Initialisiere mit den Standardwerten aus deinem Skript oder leer
    st.session_state.target_assemblies = [
        {'id': 1110, 'quantity': 2.0},
        {'id': 1400, 'quantity': 2.0},
        {'id': 1344, 'quantity': 3.0},
    ]

if 'results' not in st.session_state:
    st.session_state.results = None # Hier speichern wir die Berechnungsergebnisse

# --- UI für Eingaben (Target Assemblies) ---
st.sidebar.header("🎯 Ziel-Assemblies definieren")

# Funktion zum Hinzufügen einer neuen Zeile für Assembly-Eingabe
def add_assembly_input():
    st.session_state.target_assemblies.append({'id': 0, 'quantity': 1.0})

# Funktion zum Entfernen der letzten Assembly-Zeile
def remove_assembly_input():
    if len(st.session_state.target_assemblies) > 0:
        st.session_state.target_assemblies.pop()

# Buttons zum Hinzufügen/Entfernen im Sidebar
col1, col2 = st.sidebar.columns(2)
with col1:
    st.button("➕ Zeile hinzufügen", on_click=add_assembly_input, use_container_width=True)
with col2:
    st.button("➖ Letzte entfernen", on_click=remove_assembly_input, use_container_width=True)


# Zeige Eingabefelder für jede Assembly in der Liste
assembly_inputs = []
for i, assembly in enumerate(st.session_state.target_assemblies):
    cols = st.sidebar.columns([0.4, 0.4, 0.2]) # Spalten für ID, Menge, (Platzhalter oder Löschbutton wäre hier möglich)
    with cols[0]:
        # Verwende eindeutige Keys für jedes Widget
        new_id = st.number_input(f"Part ID #{i+1}", value=assembly['id'], key=f"id_{i}", min_value=1, step=1, help="Die InvenTree Part ID der Assembly.")
    with cols[1]:
        new_qty = st.number_input(f"Menge #{i+1}", value=assembly['quantity'], key=f"qty_{i}", min_value=0.01, step=0.1, format="%.2f", help="Benötigte Menge dieser Assembly.")

    # Aktualisiere den Session State direkt (Streamlit führt das Skript bei jeder Interaktion neu aus)
    st.session_state.target_assemblies[i]['id'] = new_id
    st.session_state.target_assemblies[i]['quantity'] = new_qty


# --- Berechnungs-Button und Logik-Aufruf ---
st.header("⚙️ Berechnung starten")

if st.button(" Teilebedarf berechnen", type="primary", use_container_width=True):
    # Bereite das Dictionary für die Logik-Funktion vor
    targets_dict = {int(a['id']): float(a['quantity']) for a in st.session_state.target_assemblies if a['id'] > 0 and a['quantity'] > 0}

    if not targets_dict:
        st.warning("⚠️ Bitte mindestens eine gültige Assembly (ID > 0, Menge > 0) eingeben.")
    else:
        with st.spinner("⏳ Berechne benötigte Teile... (Dies kann bei komplexen BOMs dauern)"):
            try:
                # Rufe die Kernlogik auf
                parts_to_order = calculate_required_parts(api, targets_dict)
                st.session_state.results = parts_to_order # Speichere Ergebnisse im Session State
                if not parts_to_order:
                     st.success("✅ Alle benötigten Komponenten sind ausreichend auf Lager.")
                else:
                     st.success(f"✅ Berechnung abgeschlossen. {len(parts_to_order)} Teile müssen bestellt werden.")

            except Exception as e:
                st.error(f"Ein Fehler ist während der Berechnung aufgetreten: {e}")
                log.error("Fehler während calculate_required_parts in Streamlit App:", exc_info=True)
                st.session_state.results = None # Setze Ergebnisse bei Fehler zurück


# --- Ergebnisse anzeigen ---
st.header("📋 Ergebnisse: Benötigte Teile")

if st.session_state.results is not None:
    if len(st.session_state.results) > 0:
        # Konvertiere die Ergebnisliste in einen Pandas DataFrame für bessere Darstellung
        df = pd.DataFrame(st.session_state.results)
        # Passe Spaltenreihenfolge und -namen an (optional)
        df_display = df[['pk', 'name', 'required', 'in_stock', 'to_order']]
        df_display.columns = ['Part ID', 'Name', 'Benötigt', 'Auf Lager', 'Zu bestellen']

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # Optional: Download-Button für CSV oder Markdown
        csv = df_display.to_csv(index=False).encode('utf-8')
        st.download_button(
           label="💾 Ergebnisse als CSV herunterladen",
           data=csv,
           file_name='inventree_order_list.csv',
           mime='text/csv',
        )

        # Optional: Markdown-Ausgabe (wie im Original-Skript)
        # Hier könntest du die save_results_to_markdown Funktion importieren und nutzen
        # oder den Markdown-String direkt erstellen und mit st.markdown anzeigen/downloaden.

    elif len(st.session_state.results) == 0 and st.session_state.results is not None:
        # Explizite Nachricht, wenn die Berechnung lief, aber nichts bestellt werden muss.
        # Die Success-Nachricht oben deckt das zwar ab, aber hier nochmal klar im Ergebnisbereich.
        st.info("👍 Alle Teile auf Lager, keine Bestellung notwendig.")
else:
    st.info("Klicke auf 'Teilebedarf berechnen', um die Ergebnisse anzuzeigen.")

# Optional: Auto-refresh (siehe IDEA.md für Details zur Implementierung)
# from streamlit_autorefresh import st_autorefresh
# st_autorefresh(interval=300000, limit=None, key="freshening")