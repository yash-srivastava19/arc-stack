from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("arc-prs")
except PackageNotFoundError:  # source checkout without `pip install -e .`
    __version__ = "0.0.0+dev"
