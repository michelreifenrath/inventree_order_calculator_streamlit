"""
Facade module for InvenTree order calculation logic.

Exports:
    - get_recursive_bom
    - calculate_required_parts
"""

from src.bom_calculation import get_recursive_bom # Absolute import
from src.order_calculation import calculate_required_parts # Absolute import

__all__ = ["get_recursive_bom", "calculate_required_parts"]
