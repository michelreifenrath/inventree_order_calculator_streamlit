"""Database helper functions for saving and loading assembly configurations."""

import json
import sqlite3
from typing import List, Dict, Optional
import streamlit as st
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db() -> None:
    """Initialize SQLite database for saved assemblies."""
    try:
        conn = sqlite3.connect('data/assemblies.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS saved_assemblies
                     (name TEXT PRIMARY KEY, 
                      assemblies TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        st.error("Fehler beim Initialisieren der Datenbank!")
    finally:
        conn.close()

def save_current_assemblies(name: str) -> bool:
    """
    Save current assembly selection to database.
    
    Args:
        name (str): Name for the saved configuration
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    if "target_assemblies" not in st.session_state:
        st.error("Keine Baugruppen zum Speichern vorhanden.")
        return False
    
    try:
        conn = sqlite3.connect('data/assemblies.db')
        c = conn.cursor()
        assemblies_json = json.dumps(st.session_state.target_assemblies)
        c.execute('INSERT OR REPLACE INTO saved_assemblies (name, assemblies) VALUES (?, ?)',
                  (name, assemblies_json))
        conn.commit()
        logger.info(f"Successfully saved assembly configuration: {name}")
        return True
    except Exception as e:
        logger.error(f"Error saving assemblies: {e}")
        st.error("Fehler beim Speichern der Baugruppen!")
        return False
    finally:
        conn.close()

def load_saved_assemblies(name: str) -> bool:
    """
    Load saved assembly selection from database.
    
    Args:
        name (str): Name of the configuration to load
        
    Returns:
        bool: True if load was successful, False otherwise
    """
    try:
        conn = sqlite3.connect('data/assemblies.db')
        c = conn.cursor()
        c.execute('SELECT assemblies FROM saved_assemblies WHERE name = ?', (name,))
        result = c.fetchone()
        
        if result:
            st.session_state.target_assemblies = json.loads(result[0])
            logger.info(f"Successfully loaded assembly configuration: {name}")
            return True
        else:
            st.error(f"Keine gespeicherte Auswahl mit Namen '{name}' gefunden.")
            return False
    except Exception as e:
        logger.error(f"Error loading assemblies: {e}")
        st.error("Fehler beim Laden der Baugruppen!")
        return False
    finally:
        conn.close()

def get_saved_assembly_names() -> List[str]:
    """
    Get list of all saved assembly selection names.
    
    Returns:
        List[str]: List of saved configuration names
    """
    try:
        conn = sqlite3.connect('data/assemblies.db')
        c = conn.cursor()
        c.execute('SELECT name FROM saved_assemblies ORDER BY created_at DESC')
        names = [row[0] for row in c.fetchall()]
        return names
    except Exception as e:
        logger.error(f"Error fetching saved assembly names: {e}")
        return []
    finally:
        conn.close()

def delete_saved_assembly(name: str) -> bool:
    """
    Delete a saved assembly configuration.
    
    Args:
        name (str): Name of the configuration to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        conn = sqlite3.connect('data/assemblies.db')
        c = conn.cursor()
        c.execute('DELETE FROM saved_assemblies WHERE name = ?', (name,))
        conn.commit()
        logger.info(f"Successfully deleted assembly configuration: {name}")
        return True
    except Exception as e:
        logger.error(f"Error deleting assembly configuration: {e}")
        return False
    finally:
        conn.close()