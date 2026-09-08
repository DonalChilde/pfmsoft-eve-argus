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

# Clean local git branches - removes local branches that are not tracked on origin.
git-cleanup force="":
    @echo "Checking for stale local branches..."
    @echo "Pass --force to delete unmerged branches."
    @delete_command="git branch -d"; \
    if [ "{{force}}" = "--force" ]; then delete_command="git branch -D"; fi; \
    branches=$(git fetch --prune >/dev/null 2>&1 && git branch -vv | awk '/: gone]/ {print $1}'); \
    if [ -n "$branches" ]; then \
        echo "Branches eligible for deletion:"; \
        printf '%s\n' "$branches"; \
        printf "Delete these branches? [y/N] "; \
        read answer; \
        case "$answer" in \
            [Yy]|[Yy][Ee][Ss]) $delete_command $branches ;; \
            *) echo "Aborted."; exit 1 ;; \
        esac; \
    else \
        echo "No stale local branches found."; \
    fi