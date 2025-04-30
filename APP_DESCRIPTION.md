# Beschreibung der Anwendung: InvenTree Order Calculator

## Zweck der Anwendung

Die Anwendung "InvenTree Order Calculator" ist ein Werkzeug für die Produktionsplanung, das auf Basis ausgewählter Endprodukte (Ziel-Baugruppen) und deren gewünschter Mengen ermittelt, welche Rohmaterialien/Komponenten bestellt und welche Zwischenbaugruppen produziert werden müssen. Es interagiert direkt mit einer InvenTree-Instanz, um Stücklisten (BOMs), Lagerbestände und Bestelldaten abzurufen.

## Ablauf und Benutzeroberfläche (`src/app.py`)

1.  **Verbindung & Setup:** Die App verbindet sich beim Start mit der InvenTree-API unter Verwendung von URL und Token aus einer `.env`-Datei.
2.  **Auswahl:** Der Benutzer wählt über eine Streamlit-Oberfläche eine oder mehrere Ziel-Baugruppen (typischerweise Endprodukte) aus einer vordefinierten InvenTree-Kategorie aus und gibt die jeweils benötigte Menge an.
3.  **Filter:** Optional können Filter angewendet werden, um z.B. Teile von bestimmten Lieferanten oder Herstellern von der finalen Bestellliste auszuschließen.
4.  **Berechnungsstart:** Ein Klick auf "Teilebedarf berechnen" löst die Kernlogik aus.
5.  **Ergebnisanzeige:** Die Ergebnisse werden in zwei Haupttabellen angezeigt:
    *   Eine Liste der zu bestellenden Basiskomponenten mit Details wie benötigte Menge, verfügbarer Bestand, Saldo, zu bestellende Menge und zugehörige offene Bestellungen.
    *   Eine Liste der zu produzierenden Unterbaugruppen mit Details wie Gesamtbedarf, verfügbarer Bestand, Menge "Im Bau" (in offenen Fertigungsaufträgen), Saldo und zu bauende Menge.

## Kernberechnungslogik (`src/order_calculation.py` & `src/bom_calculation.py`)

Die Berechnung des tatsächlichen Bedarfs ist komplex, da Lagerbestände, externer Bedarf (z.B. aus Verkaufsaufträgen) und der Bedarf an Unterbaugruppen berücksichtigt werden müssen. Dies geschieht in einem **Zwei-Pass-Verfahren**:

1.  **Pass 1: Brutto-Bedarfsermittlung (`get_recursive_bom` ohne Bestandsprüfung):**
    *   **Ziel:** Identifizierung *aller* Teile (Basiskomponenten und Unterbaugruppen) und deren *Gesamtmengen*, die theoretisch für die Ziel-Baugruppen benötigt werden, **unabhängig** von Lagerbeständen oder externem Bedarf.
    *   **Wie:** Die Funktion `get_recursive_bom` durchläuft die Stücklisten der Ziel-Baugruppen rekursiv. Für jede gefundene Unterbaugruppe wird die Rekursion fortgesetzt, ohne den Bestand zu prüfen. Der Bedarf an Basiskomponenten wird aufsummiert.
    *   **Ergebnis:** Eine Liste aller beteiligten Teile und der Brutto-Gesamtbedarf für jede Unterbaugruppe.

2.  **Zwischenschritt: Datenabruf:**
    *   Für alle in Pass 1 identifizierten Teile wird der externe Bedarf (`required`) aus InvenTree abgerufen (`Part.getRequirements()`).
    *   Details wie Lagerbestand, Hersteller etc. werden ebenfalls für alle Teile geholt (`get_final_part_data`).

3.  **Pass 2: Netto-Bedarfsermittlung (`get_recursive_bom` mit Bestandsprüfung):**
    *   **Ziel:** Berechnung des *Netto*-Bedarfs an Basiskomponenten und Ermittlung, welche Unterbaugruppen tatsächlich gebaut werden müssen.
    *   **Wie:** `get_recursive_bom` wird erneut aufgerufen, diesmal **mit** den Informationen über Lagerbestände und externen Bedarf. Wenn die Funktion auf eine Unterbaugruppe trifft, prüft sie: `Verfügbarer Bestand = Lagerbestand - Externer Bedarf`.
        *   Wenn `Verfügbarer Bestand >= Benötigte Menge der Unterbaugruppe`, wird die Rekursion für diesen Zweig **abgebrochen**, da genügend Unterbaugruppen vorhanden sind.
        *   Wenn `Verfügbarer Bestand < Benötigte Menge`, wird die Rekursion fortgesetzt, aber **nur für die fehlende Menge (`to_build`)** der Unterbaugruppe.
    *   **Ergebnis:** Der Netto-Bedarf an Basiskomponenten, der nach Berücksichtigung aller verfügbaren Bestände (auch von Unterbaugruppen) übrig bleibt.

4.  **Finale Berechnung & Listen:**
    *   **Bestellmenge (`to_order`) für Basiskomponenten:** `max(0, Netto-Bedarf - (Verfügbarer Bestand - Externer Bedarf))`
    *   **Produktionsmenge (`to_build`) für Unterbaugruppen:** `max(0, Brutto-Gesamtbedarf - (Verfügbarer Bestand - Externer Bedarf))`
    *   Offene Bestellungen (Purchase Orders) für die zu bestellenden Teile werden abgerufen (`_fetch_purchase_order_data`) und angezeigt.
    *   Die finalen Listen werden erstellt, gefiltert und an die UI übergeben.

## Zusammenfassung

Die Anwendung löst komplexe Stücklisten rekursiv auf und führt eine differenzierte Bedarfsrechnung durch, die sowohl Lagerbestände als auch externen Bedarf berücksichtigt, um präzise Bestell- und Produktionsvorschläge zu generieren. Die Zwei-Pass-Strategie ist entscheidend, um den Bedarf korrekt zu ermitteln, wenn Unterbaugruppen mehrfach in verschiedenen Ebenen der Stückliste vorkommen.