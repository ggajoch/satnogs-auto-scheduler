from ._version import get_versions
from .satellite import Satellite  # noqa

__version__ = get_versions()['version']
del get_versions
