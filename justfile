# The command run by default
default:
    @just --list

# Clean Python cache files
clean-py: 
    @echo "Cleaning Python cache files..."
    find . -name '__pycache__' -exec rm -fr {} +

# Build sphinx docs
docs:
    @echo "Building Sphinx documentation..."
    sphinx-apidoc -f -o ./docs/source/documentation/api-generated/ ./src/eve_argus/
    sphinx-build -M html docs/source docs/build --fail-on-warning