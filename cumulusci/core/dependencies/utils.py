from logging import Logger
from typing import NamedTuple, Optional

from cumulusci.core.config.org_config import OrgConfig
from cumulusci.core.config.project_config import BaseProjectConfig

# data structure mimicking a task for use with the metadata API classes


class TaskContext(NamedTuple):
    org_config: OrgConfig
    project_config: BaseProjectConfig
    logger: Logger
    task: Optional[object] = None  # Reference to the task object that may contain shared_package_state
