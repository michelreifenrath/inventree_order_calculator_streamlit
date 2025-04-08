# Plan: Gruppierung & Farbliche Hervorhebung der Ausgabeliste nach Eingangsteil

## Ziel
Die Ausgabeliste der zu bestellenden Teile soll **gruppiert** und **farblich hervorgehoben** werden, basierend darauf, zu welchem Eingangsteil (Input-Assembly) sie gehören.

---

## Übersicht

- **Backend:** BOM-Berechnung anpassen, sodass die Zugehörigkeit zu Eingangsteilen erhalten bleibt.
- **Frontend:** Ausgabe gruppieren & farblich hervorheben.

---

## Schritt-für-Schritt-Plan

### 1. Datenstruktur anpassen

- Statt einer flachen `defaultdict[int, float]` wird eine **verschachtelte Struktur** verwendet:
  
```python
required_components: dict[int, dict[int, float]]
# input_assembly_id -> {component_id -> quantity}
```

- Beim initialen Aufruf von `get_recursive_bom` wird die ID des Eingangsteils als `root_input_id` übergeben.
- Diese ID wird **rekursiv weitergereicht**.
- Mengen werden **pro Eingangsteil** aufsummiert.

---

### 2. Rekursive BOM-Berechnung erweitern

- `get_recursive_bom` erhält neuen Parameter `root_input_id`.
- Beim Aufruf:
  - Wenn Unterbaugruppe: rekursiver Aufruf mit **gleichem** `root_input_id`.
  - Wenn Basis-Komponente: Menge unter `required_components[root_input_id][component_id]` aufsummieren.

---

### 3. Ausgabe-Liste erstellen

- Für jede Gruppe (Eingangsteil) werden die zugehörigen Komponenten mit Mengen, Lagerbestand, Bestellmenge gesammelt.
- Jeder Komponente wird die **Input-Assembly-ID** (und optional Name) zugeordnet.
- Ergebnis: Liste von Dicts, **inklusive Gruppenzugehörigkeit**.

---

### 4. Darstellung in Streamlit

- Die Liste wird **nach Eingangsteil gruppiert**.
- Für jede Gruppe:
  - **Farblich hervorgehobener Header** (z.B. farbiger Hintergrund oder Text).
  - Tabelle oder Liste der zugehörigen Komponenten.
- Farben werden aus einer **Palette** gewählt und zyklisch verwendet.

---

## Mermaid Diagramm

```mermaid
flowchart TD
    A[User inputs assemblies] --> B[calculate_required_parts]
    B --> C{For each input assembly}
    C --> D[get_recursive_bom (pass root_input_id)]
    D --> E{Is assembly?}
    E -- Yes --> D
    E -- No --> F[Accumulate qty under root_input_id]
    F --> G[Final nested dict: input_id -> {component_id: qty}]
    G --> H[Fetch part details]
    H --> I[Build output list with input_id info]
    I --> J[Group by input_id in UI]
    J --> K[Display each group with unique color highlight]
```

---

## Vorteile

- **Übersichtlicher:** Nutzer sehen sofort, welche Teile zu welchem Eingangsteil gehören.
- **Intuitiv:** Farbliche Trennung erleichtert das Erfassen.
- **Flexibel:** Erweiterbar für weitere Gruppierungs- oder Sortierkriterien.

---

## Nächste Schritte

- Backend-Logik anpassen (rekursive Funktion & Datenstruktur).
- Ausgabe-Liste erweitern.
- Streamlit-UI anpassen (Gruppierung & Farbhervorhebung).
- Tests ergänzen.