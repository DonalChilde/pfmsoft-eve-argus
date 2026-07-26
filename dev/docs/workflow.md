# Dev workflow notes

TODO: update for release.sh script, dependency-report.py, zensical docs

## Feature dev steps

- Ensure dev branch is current!
- make a feature branch from the dev branch
- `scriv create` to make a scriv fragment. Update fragment with expected feature details.
- code the feature.
- ensure tests are written and pass.
- update docs.
- update scriv fragment with ACTUAL changes.
- merge feature branch to dev

# Release steps

- Ensure dev branch is current!
- Make a release branch from the dev branch
- Make a PR for the release branch if using GitHub PRs. ENSURE USING THE DEV AND FEATURE BRANCHES!
- Update the version in pyproject.toml, and in the `__init__.py` file
- Use `scriv collect` to update changelog. Check and edit as necessary.
  - Update the Unreleased compare version to latest release tag
  - Update compare/_previous_version_tag_
  - Update issues and pull requests as needed
- ensure tests pass
- check docs are up to date.
- Ensure local branch pushed to origin
- Accept PR, and merge to dev. ENSURE MERGING TO THE CORRECT BRANCH!
- If not using a PR through Github, merge feature branch into dev.
- Merge dev into main
- tag the release using `0.0.0` format `git tag -a <tag_name> -m "Tag message"`
- push tag to origin with `git push origin <tagname>`
- make Github Release
