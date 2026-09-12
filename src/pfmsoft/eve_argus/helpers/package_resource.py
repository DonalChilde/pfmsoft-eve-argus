"""Helpers for working with package resources."""

from importlib.resources import files as resource_files


def load_package_resouce_text(package: str, resource_name: str) -> str:
    """Load a resource from the package as text.

    Args:
        package: Package name where the resource is located.
        resource_name: Name of the resource file to load.

    Returns:
        The contents of the resource file as a string.
    """
    return resource_files(package).joinpath(resource_name).read_text()
