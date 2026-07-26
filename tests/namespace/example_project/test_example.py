"""Tests for the example_project namespace package."""

from namespace.example_project import main


def test_successful_example():
    # main returns "Hello from namespace.example_project.main()!"

    assert main() == "Hello from namespace.example_project.main()!"
