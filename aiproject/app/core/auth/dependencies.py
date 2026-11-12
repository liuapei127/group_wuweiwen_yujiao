"""Compatibility imports. Use app.core.security for new code."""
from app.core.security.dependencies import EmployeePrincipal, require_employee

__all__ = ["EmployeePrincipal", "require_employee"]
