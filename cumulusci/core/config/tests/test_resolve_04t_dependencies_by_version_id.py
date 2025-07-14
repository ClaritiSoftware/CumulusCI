import pytest
from collections import defaultdict
from unittest import mock

from cumulusci.core.config.org_config import OrgConfig, VersionInfo
from cumulusci.core.dependencies.dependencies import (
    PackageNamespaceVersionDependency,
    PackageVersionIdDependency,
)
from cumulusci.utils.version_strings import StrictVersion


class TestResolve04tDependenciesByVersionId:
    def test_resolve_04t_dependencies_by_version_id(self):
        """Test that resolve_04t_dependencies checks for version ID when namespace@version is not found"""
        config = OrgConfig({}, "test")
        
        # Set up installed packages with a version that doesn't exactly match the requested version string
        # but has the same version ID
        installed_packages = defaultdict(list)
        installed_packages["dep"].append(VersionInfo("04t000000000001AAA", StrictVersion("1.0.1")))
        # Note: no "dep@1.0" entry
        config._installed_packages = installed_packages
        
        # Mock has_minimum_package_version to return True
        config.has_minimum_package_version = mock.Mock(return_value=True)
        
        # Call the method with a dependency that specifies version "1.0"
        result = config.resolve_04t_dependencies(
            [PackageNamespaceVersionDependency(namespace="dep", version="1.0")]
        )
        
        # Verify that has_minimum_package_version was called with the correct arguments
        config.has_minimum_package_version.assert_called_once_with("dep", "1.0")
        
        # Verify that the dependency was resolved correctly using the version ID
        assert result == [PackageVersionIdDependency(version_id="04t000000000001AAA")]

    def test_resolve_04t_dependencies_by_version_id_not_minimum_version(self):
        """Test that resolve_04t_dependencies fails when the installed version is less than the requested version"""
        config = OrgConfig({}, "test")
        
        # Set up installed packages with a version
        installed_packages = defaultdict(list)
        installed_packages["dep"].append(VersionInfo("04t000000000001AAA", StrictVersion("1.0.0")))
        # Note: no "dep@1.1" entry
        config._installed_packages = installed_packages
        
        # Mock has_minimum_package_version to return False
        config.has_minimum_package_version = mock.Mock(return_value=False)
        
        # Call the method with a dependency that specifies version "1.1" (higher than installed)
        with pytest.raises(Exception) as e:
            config.resolve_04t_dependencies(
                [PackageNamespaceVersionDependency(namespace="dep", version="1.1")]
            )
        
        # Verify that has_minimum_package_version was called with the correct arguments
        config.has_minimum_package_version.assert_called_once_with("dep", "1.1")
        
        # Verify that the exception message contains the expected text
        assert "Could not find 04t id for package dep@1.1" in str(e.value)
