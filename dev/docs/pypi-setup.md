# Publish to pypi

## Steps to setup publishing package

## Github Action to Pulishe on Release

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  build-and-publish:
    name: Build and publish Python distribution
    runs-on: ubuntu-latest

    environment:
      name: pypi
      url: https://pypi.org/project/PROJECT_NAME/ # Update this to the project name on pypi

    permissions:
      id-token: write # Required for PyPI Trusted Publishing
      contents: read # Required to checkout the repository

    steps:
      - name: Checkout code
        uses: actions/checkout@v7

      - name: Set up uv
        uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install

      - name: Build source and wheel distributions
        run: uv build

      - name: Publish package to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

```