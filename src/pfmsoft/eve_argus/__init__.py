"""Example project namespace package."""

from importlib.metadata import version

__project_namespace__ = "pfmsoft"
__author__ = "Chad Lowe"
__email__ = "pfmsoft.dev@gmail.com"
__app_name__ = "pfmsoft-eve-argus"  # must match the name in pyproject.toml
__description__ = "A namespaced project template for Python projects using namespaces."
__version__ = version(__app_name__)
__release__ = __version__
__url__ = "https://github.com/DonalChilde/pfmsoft-eve-argus"
__license__ = "MIT"
