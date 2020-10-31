from .satellite import Satellite  # noqa
from .tle import Twolineelement  # noqa

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions
