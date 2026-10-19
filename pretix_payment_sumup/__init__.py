from importlib.metadata import PackageNotFoundError, version

try:
    # Set from the git tag by the release workflow, see pyproject.toml.
    __version__ = version("pretix-payment-sumup")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"
