import unittest
from unittest import mock

from cumulusci.core.config.org_config import OrgConfig
from cumulusci.core.shared_state import SharedPackageState
from cumulusci.salesforce_api.package_install import install_package_by_version_id, install_package_by_namespace_version, PackageInstallOptions


class TestSharedPackageState(unittest.TestCase):
    """Tests for the SharedPackageState class"""

    def setUp(self):
        self.org_config = mock.MagicMock(spec=OrgConfig)
        self.org_config.installed_packages = {}
        self.org_config.has_minimum_package_version.return_value = False
        self.shared_state = SharedPackageState()
        self.shared_state.set_org_config(self.org_config)
        
    def test_has_package_no_packages(self):
        """Test has_package with no packages installed"""
        self.assertFalse(self.shared_state.has_package("test"))
        
    def test_has_package_with_package(self):
        """Test has_package with a package installed"""
        version_info = mock.MagicMock()
        version_info.number = "1.0"
        self.shared_state.add_package("test", version_info)
        self.assertTrue(self.shared_state.has_package("test"))
        
    def test_has_package_with_version(self):
        """Test has_package with version check"""
        version_info = mock.MagicMock()
        version_info.number = "1.0"
        self.shared_state.add_package("test", version_info)
        self.assertTrue(self.shared_state.has_package("test", "1.0"))
        self.assertTrue(self.shared_state.has_package("test", "0.9"))
        self.assertFalse(self.shared_state.has_package("test", "1.1"))
        
    def test_get_package_info(self):
        """Test get_package_info"""
        version_info = mock.MagicMock()
        self.shared_state.add_package("test", version_info)
        self.assertEqual([version_info], self.shared_state.get_package_info("test"))
        self.assertIsNone(self.shared_state.get_package_info("nonexistent"))


class TestPackageInstallWithSharedState(unittest.TestCase):
    """Tests for package installation with shared state"""
    
    def setUp(self):
        self.org_config = mock.MagicMock(spec=OrgConfig)
        self.org_config.installed_packages = {}
        self.org_config.has_minimum_package_version.return_value = False
        self.project_config = mock.MagicMock()
        self.shared_state = SharedPackageState()
        self.shared_state.set_org_config(self.org_config)
        
    @mock.patch("cumulusci.salesforce_api.package_install.retry")
    def test_install_package_by_version_id_with_shared_state(self, retry_mock):
        """Test that install_package_by_version_id uses shared state"""
        # First installation should proceed
        install_package_by_version_id(
            self.project_config,
            self.org_config,
            "04t000000000000",
            PackageInstallOptions(),
            shared_package_state=self.shared_state,
        )
        self.assertEqual(1, retry_mock.call_count)
        
        # Setup mock for installed package
        version_info = mock.MagicMock()
        self.org_config.installed_packages = {"04t000000000000": [version_info]}
        
        # Update shared state
        self.shared_state.add_package("04t000000000000", version_info)
        
        # Second installation should be skipped
        install_package_by_version_id(
            self.project_config,
            self.org_config,
            "04t000000000000",
            PackageInstallOptions(),
            shared_package_state=self.shared_state,
        )
        # Retry should not be called again
        self.assertEqual(1, retry_mock.call_count)
        
    @mock.patch("cumulusci.salesforce_api.package_install.retry")
    def test_install_package_by_namespace_version_with_shared_state(self, retry_mock):
        """Test that install_package_by_namespace_version uses shared state"""
        # First installation should proceed
        install_package_by_namespace_version(
            self.project_config,
            self.org_config,
            "testns",
            "1.0",
            PackageInstallOptions(),
            shared_package_state=self.shared_state,
        )
        self.assertEqual(1, retry_mock.call_count)
        
        # Setup mock for installed package
        version_info = mock.MagicMock()
        version_info.number = "1.0"
        self.org_config.installed_packages = {"testns": [version_info]}
        
        # Update shared state
        self.shared_state.add_package("testns", version_info)
        self.shared_state.add_package("testns@1.0", version_info)
        
        # Second installation should be skipped
        install_package_by_namespace_version(
            self.project_config,
            self.org_config,
            "testns",
            "1.0",
            PackageInstallOptions(),
            shared_package_state=self.shared_state,
        )
        # Retry should not be called again
        self.assertEqual(1, retry_mock.call_count)
