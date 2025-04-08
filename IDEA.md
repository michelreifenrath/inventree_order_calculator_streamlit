Okay, lass uns dein Python-Skript Schritt für Schritt in eine interaktive Streamlit-Webanwendung umwandeln. Streamlit eignet sich hier gut, weil es sehr Python-freundlich ist und schnell zu Ergebnissen führt, besonders für datenorientierte Aufgaben und Dashboards.

**Ziel:**
Eine Web-App, die:
1.  Deine InvenTree URL und Token sicher entgegennimmt (oder aus der Umgebung liest).
2.  Dir erlaubt, die `TARGET_ASSEMBLY_IDS` und deren Mengen über die Oberfläche einzugeben und zu ändern.
3.  Einen Button hat, um die Berechnung zu starten.
4.  Die resultierende "Parts to Order"-Liste in einer Tabelle anzeigt.
5.  (Optional) Sich automatisch aktualisieren kann oder einen Refresh-Button hat.
6.  (Optional) Statusmeldungen/Logs anzeigt.

**Vorgehensweise:**

1.  **Installation:** Streamlit installieren.
2.  **Refactoring des Original-Skripts:** Die Kernlogik (API-Verbindung, BOM-Berechnung, Datenabruf) in Funktionen kapseln, die von der Streamlit-App aufgerufen werden können. Inputs (wie die Assembly-Liste) und Outputs (die Bestellliste) werden zu Funktionsparametern bzw. Rückgabewerten.
3.  **Streamlit App Grundgerüst:** Eine neue Python-Datei für die Streamlit-App erstellen.
4.  **Konfiguration (Secrets Management):** URL und Token sicher handhaben.
5.  **UI für Eingaben:** Streamlit-Widgets hinzufügen, um die Ziel-Assemblies und Mengen zu definieren.
6.  **Zustandsverwaltung:** `st.session_state` verwenden, um die Benutzereingaben über App-Neuausführungen hinweg zu speichern.
7.  **Berechnung auslösen:** Einen Button hinzufügen, der die refaktorierte Kernlogik aufruft.
8.  **Ergebnisse anzeigen:** Die zurückgegebene Bestellliste mit `st.dataframe` oder `st.table` darstellen.
9.  **Caching:** Streamlit's Caching nutzen, um API-Aufrufe zu beschleunigen und unnötige Neuberechnungen zu vermeiden.
10. **(Optional) Auto-Refresh / Logging:** Mechanismen für automatische Aktualisierung oder Anzeige von Logs hinzufügen.

---

**Schritt-für-Schritt Anleitung mit Beispielcode:**

**Schritt 1: Installation**

Falls noch nicht geschehen, installiere Streamlit:
```bash
pip install streamlit pandas # Pandas wird oft mit Streamlit für DataFrames genutzt
```
Du benötigst auch deine `inventree` Bibliothek:```bash
pip install inventree
```

**Schritt 2: Refactoring des Original-Skripts**

Erstelle eine neue Datei, z.B. `inventree_logic.py`, und verschiebe/passe deine Funktionen dorthin an. Wichtige Änderungen:

*   Die Funktionen sollten die `api`-Instanz als Argument erhalten, anstatt sie global anzunehmen.
*   Die Kernberechnung sollte in einer Funktion gekapselt sein, die die Ziel-Assemblies als Input nimmt und die Bestellliste als Output zurückgibt.
*   Caching wird später mit Streamlit-Dekoratoren hinzugefügt. Entferne vorerst die manuelle Cache-Logik (`part_cache`, `bom_cache`) oder passe sie an Streamlit's Caching an (empfohlen).

```python
# inventree_logic.py
import os
import sys
import logging
from collections import defaultdict
from inventree.api import InvenTreeAPI
from inventree.part import Part
from streamlit import cache_data, cache_resource # Streamlit caching importieren

# Configure logging (kann auch in der Streamlit App konfiguriert werden)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Helper Functions (angepasst für Streamlit Caching) ---

# Cache API connection - hält die Verbindung über Re-Runs offen
@cache_resource
def connect_to_inventree(url, token):
    """Connects to the InvenTree API and returns the API object."""
    log.info("Attempting to connect to InvenTree API...")
    try:
        api = InvenTreeAPI(url, token=token)
        log.info(f"Connected to InvenTree API version: {api.api_version}")
        return api
    except Exception as e:
        log.error(f"Failed to connect to InvenTree API: {e}", exc_info=True)
        # In Streamlit, it's better to raise the exception or return None and handle it in the UI
        return None

# Cache data fetching functions - vermeidet wiederholte API calls für gleiche Inputs
@cache_data(ttl=600) # Cache results for 10 minutes
def get_part_details(_api: InvenTreeAPI, part_id: int) -> dict | None:
    """Gets part details (assembly, name, stock) from API."""
    log.debug(f"Fetching part details from API for: {part_id}")
    try:
        # Stelle sicher, dass _api ein gültiges API-Objekt ist
        if not _api:
             log.error("API object is invalid in get_part_details.")
             return None
        part = Part(_api, pk=part_id)
        if not part or not part.pk:
            log.warning(f"Could not retrieve part details for ID {part_id} from API.")
            return None

        details = {
            'assembly': part.assembly,
            'name': part.name,
            'in_stock': float(part._data.get('in_stock', 0) or 0) # Ensure float, handle None
        }
        return details
    except Exception as e:
        log.error(f"Error fetching part details for ID {part_id}: {e}")
        return None

@cache_data(ttl=600)
def get_bom_items(_api: InvenTreeAPI, part_id: int) -> list | None:
    """Gets BOM items for a part ID from API."""
    log.debug(f"Fetching BOM from API for: {part_id}")
    try:
        if not _api:
             log.error("API object is invalid in get_bom_items.")
             return None
        # Check if it's an assembly first (using cached detail fetch)
        part_details = get_part_details(_api, part_id)
        if not part_details or not part_details['assembly']:
            log.debug(f"Part {part_id} is not an assembly or details failed. No BOM.")
            return [] # Return empty list for non-assemblies

        part = Part(_api, pk=part_id) # Re-fetch Part object to call method
        bom_items_raw = part.getBomItems()
        if bom_items_raw:
            bom_data = [{'sub_part': item.sub_part, 'quantity': float(item.quantity)} for item in bom_items_raw]
            return bom_data
        else:
            log.debug(f"Assembly {part_id} has an empty BOM.")
            return [] # Return empty list
    except Exception as e:
        log.error(f"Error fetching BOM items for part ID {part_id}: {e}")
        return None # Indicate failure


def get_recursive_bom(api: InvenTreeAPI, part_id: int, quantity: float, required_components: defaultdict[int, float]):
    """
    Recursively processes the BOM using cached data fetching functions.
    NOTE: This function itself is NOT cached with @cache_data because its side effect
          is modifying the 'required_components' dictionary, and caching might lead
          to stale results if underlying BOMs change rapidly between runs within the ttl.
          The caching happens on the lower-level fetch functions.
    """
    part_details = get_part_details(api, part_id) # Uses cached function
    if not part_details:
        log.warning(f"Skipping part ID {part_id} due to fetch error in recursion.")
        return

    if part_details['assembly']:
        log.debug(f"Processing assembly: {part_details['name']} (ID: {part_id}), Quantity: {quantity}")
        bom_items = get_bom_items(api, part_id) # Uses cached function
        if bom_items: # Check if BOM fetch succeeded and is not empty
            for item in bom_items:
                sub_part_id = item['sub_part']
                sub_quantity_per = item['quantity']
                total_sub_quantity = quantity * sub_quantity_per
                get_recursive_bom(api, sub_part_id, total_sub_quantity, required_components)
        elif bom_items is None: # BOM fetch failed
             log.warning(f"Could not process BOM for assembly {part_id} due to fetch error.")
    else:
        log.debug(f"Adding base component: {part_details['name']} (ID: {part_id}), Quantity: {quantity}")
        required_components[part_id] += quantity

@cache_data(ttl=600)
def get_final_part_data(_api: InvenTreeAPI, part_ids: tuple[int]) -> dict[int, dict]:
    """Fetches final data (name, stock) for a tuple of part IDs. Uses tuple for cacheability."""
    final_data = {}
    if not part_ids:
        return final_data
    # Convert tuple back to list for the API call if needed by the library
    part_ids_list = list(part_ids)

    log.info(f"Fetching final details (name, stock) for {len(part_ids_list)} base components...")
    try:
        if not _api:
             log.error("API object is invalid in get_final_part_data.")
             # Provide default unknown data on error
             for part_id in part_ids_list:
                 final_data[part_id] = {'name': f"Unknown (ID: {part_id})", 'in_stock': 0.0}
             return final_data

        # Use list() to potentially evaluate the generator if Part.list returns one
        parts_details = list(Part.list(_api, pk__in=part_ids_list))
        if parts_details:
            for part in parts_details:
                stock = part._data.get('in_stock', 0)
                final_data[part.pk] = {
                    'name': part.name,
                    'in_stock': float(stock) if stock is not None else 0.0
                }
            log.info(f"Successfully fetched batch details for {len(final_data)} parts.")
            # Check for missed IDs
            fetched_ids = set(final_data.keys())
            missed_ids = set(part_ids_list) - fetched_ids
            if missed_ids:
                log.warning(f"Could not fetch batch details for some part IDs: {missed_ids}")
                for missed_id in missed_ids:
                     final_data[missed_id] = {'name': f"Unknown (ID: {missed_id})", 'in_stock': 0.0}
        else:
            log.warning("pk__in filter returned no results for final data fetch.")
            for part_id in part_ids_list:
                 final_data[part_id] = {'name': f"Unknown (ID: {part_id})", 'in_stock': 0.0}

    except Exception as e:
        log.error(f"Error fetching batch final part data: {e}. Returning defaults.", exc_info=True)
        for part_id in part_ids_list:
             final_data[part_id] = {'name': f"Unknown (ID: {part_id})", 'in_stock': 0.0}

    log.info("Finished fetching final part data.")
    return final_data


# --- Main Calculation Function ---
def calculate_required_parts(api: InvenTreeAPI, target_assemblies: dict[int, float]) -> list[dict]:
    """
    Calculates the list of parts to order based on target assemblies.
    Returns a list of dictionaries, where each dictionary represents a part to order.
    """
    if not api:
        log.error("Cannot calculate parts: InvenTree API connection is not available.")
        return [] # Return empty list if API failed

    if not target_assemblies:
        log.info("No target assemblies provided.")
        return []

    log.info(f"Calculating required components for targets: {target_assemblies}")
    required_base_components = defaultdict(float)

    # --- Perform Recursive BOM Calculation ---
    for part_id, quantity in target_assemblies.items():
        log.info(f"Processing target assembly ID: {part_id}, Quantity: {quantity}")
        try:
            # Pass only valid IDs (int) and quantities (float)
            get_recursive_bom(api, int(part_id), float(quantity), required_base_components)
        except ValueError:
             log.error(f"Invalid ID ({part_id}) or Quantity ({quantity}). Skipping.")
             continue
        except Exception as e:
             log.error(f"Error processing assembly {part_id}: {e}", exc_info=True)
             # Decide if you want to stop or continue processing others
             continue # Continue with the next assembly

    log.info(f"Total unique base components required: {len(required_base_components)}")
    if not required_base_components:
        log.info("No base components found. Nothing to order.")
        return []

    # --- Get Final Data (Names & Stock) ---
    base_component_ids = list(required_base_components.keys())
    # Pass as tuple for cache key compatibility
    final_part_data = get_final_part_data(api, tuple(base_component_ids))

    # --- Calculate Order List ---
    parts_to_order = []
    log.info("Calculating final order quantities...")
    for part_id, required_qty in required_base_components.items():
        part_data = final_part_data.get(part_id)
        if not part_data: # Handle cases where final data fetch failed for an ID
            log.warning(f"Missing final data for Part ID {part_id}. Using defaults.")
            part_data = {'name': f"Unknown (ID: {part_id})", 'in_stock': 0.0}

        in_stock = part_data.get('in_stock', 0.0) # Default to 0 if missing
        part_name = part_data.get('name', f"Unknown (ID: {part_id})")
        to_order = required_qty - in_stock

        if to_order > 0.001: # Use a small tolerance for floating point comparisons
            parts_to_order.append({
                "pk": part_id,
                "name": part_name,
                "required": round(required_qty, 3),
                "in_stock": round(in_stock, 3),
                "to_order": round(to_order, 3)
            })

    # Sort by name
    parts_to_order.sort(key=lambda x: x["name"])
    log.info(f"Calculation finished. Parts to order: {len(parts_to_order)}")
    return parts_to_order

# (Die Funktion save_results_to_markdown kann hier bleiben oder in die Streamlit App verschoben werden,
#  wenn du einen Download-Button möchtest)
```

**Schritt 3 & 4: Streamlit App Grundgerüst & Konfiguration**

Erstelle eine Datei `app.py`. Wir nutzen Streamlit Secrets für URL/Token.

Erstelle einen Ordner `.streamlit` im selben Verzeichnis wie `app.py`.
In diesem Ordner, erstelle eine Datei `secrets.toml`:

```toml
# .streamlit/secrets.toml
INVENTREE_URL = "DEINE_INVENTREE_URL_HIER"
INVENTREE_TOKEN = "DEIN_INVENTREE_TOKEN_HIER"
```
**WICHTIG:** Füge `.streamlit/secrets.toml` zu deiner `.gitignore`-Datei hinzu, um deine Zugangsdaten nicht versehentlich in Git zu pushen!

```python
# app.py
import streamlit as st
import pandas as pd
from collections import defaultdict
import logging

# Importiere die refaktorierte Logik
from inventree_logic import connect_to_inventree, calculate_required_parts

# --- Streamlit App Konfiguration ---
st.set_page_config(page_title="InvenTree Order Calculator", layout="wide")
st.title("📊 InvenTree Order Calculator")

# Konfiguriere Logging (optional, um Logs in der Konsole zu sehen)
# Streamlit kann Logs nicht direkt in der UI anzeigen, außer man fängt sie speziell ab.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Verbindung zur API (mit Caching aus inventree_logic) ---
# Secrets werden automatisch von st.secrets geladen, wenn die Datei existiert
try:
    inventree_url = st.secrets["INVENTREE_URL"]
    inventree_token = st.secrets["INVENTREE_TOKEN"]
except KeyError:
    st.error("🚨 Fehler: INVENTREE_URL und INVENTREE_TOKEN nicht in st.secrets gefunden!")
    st.info("Bitte erstelle eine `.streamlit/secrets.toml` Datei mit deinen Zugangsdaten.")
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

```

**Schritt 5: App starten**

Öffne dein Terminal im Verzeichnis, wo `app.py` und `inventree_logic.py` liegen, und führe aus:

```bash
streamlit run app.py
```

Dein Browser sollte sich öffnen und die Web-App anzeigen.

**Schritt 6: (Optional) Auto-Refresh und Logging**

*   **Auto-Refresh:** Die einfachste Methode ist die Verwendung einer Drittanbieter-Komponente wie `streamlit-autorefresh`.
    *   Installieren: `pip install streamlit-autorefresh`
    *   In `app.py` importieren: `from streamlit_autorefresh import st_autorefresh`
    *   Am Ende der App aufrufen: `count = st_autorefresh(interval=300000, limit=None, key="freshening") # 300000 ms = 5 Minuten`
        Dies wird die App alle 5 Minuten neu laden. Beachte, dass dies auch eine neue Berechnung auslösen kann, wenn du keinen "Berechnen"-Button hättest. Mit dem Button löst der Refresh nur dann eine Neuberechnung aus, wenn sich die Eingaben seit der letzten Berechnung *und* dem letzten Refresh geändert haben (aufgrund des Cachings). Ein expliziter Refresh-Button (`st.button("Refresh Data")`) könnte sinnvoller sein, wenn du nur bei Bedarf neu laden willst.
*   **Logging:** Streamlit zeigt `print()` und `logging` Ausgaben standardmäßig in der Konsole an, wo du `streamlit run` gestartet hast. Um Logs in der UI anzuzeigen, müsstest du sie komplexer abfangen (z.B. mit einem `logging.StreamHandler`, der in ein `st.text_area` schreibt), was den Code aber deutlich komplizierter macht. Für den Anfang reicht oft der Blick in die Konsole.

---

Diese Schritte sollten dir eine funktionierende Web-GUI für dein Skript geben. Du kannst das Layout und die Widgets nach Belieben weiter anpassen.