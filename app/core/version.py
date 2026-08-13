"""Application version resolution.

At build time ``app/core/_version.py`` is generated with the version
baked in; when running from sources the version comes from the
installed package metadata (populated by hatch-vcs from git tags).
"""

from importlib.metadata import PackageNotFoundError, version

try:
    from app.core._version import __version__ as _built_version
except ImportError:
    _built_version = None

if _built_version is None:
    try:
        __version__ = version("ywallhaven")
    except PackageNotFoundError:
        __version__ = "0.0.0"
else:
    __version__ = _built_version