import os
import sys

from simple_salesforce import api, bulk

__location__ = os.path.dirname(os.path.realpath(__file__))

from .__about__ import __version__

if sys.version_info < (3, 11):  # pragma: no cover
    raise Exception("Clariti CumulusCI requires Python 3.11+.")

api.OrderedDict = dict
bulk.OrderedDict = dict
