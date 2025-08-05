"""Shared state management for CumulusCI tasks."""

from typing import Dict, List, Optional, Any
from collections import defaultdict

from cumulusci.core.config.org_config import OrgConfig


class SharedPackageState:
    """Maintains package installation state across repository contexts.
    
    This class provides a centralized registry of installed packages that persists
    across different repository contexts when using cross-project source functionality.
    It helps prevent duplicate package installations by tracking what's already been
    installed in the org during the current CumulusCI session.
    """
    
    def __init__(self):
        self._installed_packages = None
        self._org_config = None
        
    def set_org_config(self, org_config: OrgConfig):
        """Initialize or update state from org config.
        
        Args:
            org_config: The OrgConfig instance to use for initialization
        """
        self._org_config = org_config
        # Initialize with current org state
        self._installed_packages = org_config.installed_packages.copy()
    
    def has_package(self, identifier: str, version: Optional[str] = None) -> bool:
        """Check if a package is installed with optional version check.
        
        Args:
            identifier: Package identifier (namespace, version_id, or namespace@version)
            version: Optional version string to check against
            
        Returns:
            True if the package is installed (and meets version requirements if specified)
        """
        if not self._installed_packages:
            return False
            
        installed = self._installed_packages.get(identifier)
        if not installed:
            return False
            
        if version and len(installed) == 1:
            return installed[0].number >= version
            
        return True
        
    def add_package(self, identifier: str, version_info: Any):
        """Record a newly installed package.
        
        Args:
            identifier: Package identifier (namespace, version_id, or namespace@version)
            version_info: The version info object to store
        """
        if not self._installed_packages:
            self._installed_packages = defaultdict(list)
            
        self._installed_packages[identifier].append(version_info)
        
        # Force org_config to refresh its package list on next access
        if self._org_config:
            self._org_config.reset_installed_packages()
            
    def get_package_info(self, identifier: str) -> Optional[List]:
        """Get version info for an installed package.
        
        Args:
            identifier: Package identifier (namespace, version_id, or namespace@version)
            
        Returns:
            List of version info objects or None if not found
        """
        return self._installed_packages.get(identifier) if self._installed_packages else None
