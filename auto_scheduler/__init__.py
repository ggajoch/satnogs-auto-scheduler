from ._version import get_versions
from .satellite import Satellite  # noqa
from .tle import Twolineelement  # noqa

__version__ = get_versions()['version']
del get_versions
