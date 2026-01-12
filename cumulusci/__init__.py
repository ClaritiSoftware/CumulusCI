import os
import sys
import warnings
from importlib.metadata import PackageNotFoundError, version

# Suppress pkg_resources deprecation warning from PyFilesystem (fs) package
# See: https://github.com/PyFilesystem/pyfilesystem2/issues/577
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

from simple_salesforce import api, bulk

__location__ = os.path.dirname(os.path.realpath(__file__))

try:
    __version__ = version("cumulusci")
except PackageNotFoundError:
    __version__ = "unknown"

if sys.version_info < (3, 8):  # pragma: no cover
    raise Exception("CumulusCI requires Python 3.8+.")

api.OrderedDict = dict
bulk.OrderedDict = dict
