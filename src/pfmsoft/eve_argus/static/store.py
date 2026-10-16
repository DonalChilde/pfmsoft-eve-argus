"""Code for managing the static db store.

The static db store is a directory containing static database files, and a manifest file
linking file paths with build numbers and release dates.

The store should provide file paths by build number, and default to the latest build if
no build number is specified.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import RootModel

from pfmsoft.eve_argus.helpers.connection_helpers import init_database
from pfmsoft.eve_argus.static.query_helpers import load_table_definitions


@dataclass(slots=True, kw_only=True)
class ManifestEntry:
    build_number: int
    release_date: str
    file_name: str


@dataclass(slots=True, kw_only=True)
class StaticManifest:
    entries: dict[int, ManifestEntry]
    """Static manifest containing a mapping of build numbers to manifest entries."""

    def serialize(self, indent: int | None = 2) -> str:
        """Serialize the static manifest to a JSON string."""
        return StaticManifestRoot(root=self).model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, json_str: str) -> StaticManifest:
        """Deserialize a JSON string to a StaticManifest instance."""
        return StaticManifestRoot.model_validate_json(json_str).root


StaticManifestRoot = RootModel[StaticManifest]


class StaticStore:
    """Class for managing the static db store."""

    def __init__(self, store_path: Path):
        """Initialize the static store with the given directory path."""
        self.store_path = store_path
        self._ensure_store_path()
        self.manifest_path = self.store_path / "manifest.json"
        self._ensure_manifest_file()
        self.manifest = self._load_manifest()
        self._ensure_entries_exist()

    def _ensure_store_path(self):
        """Ensure the store path exists and is a directory."""
        if not self.store_path.exists():
            raise FileNotFoundError(f"Store path not found: {self.store_path}")
        if not self.store_path.is_dir():
            raise NotADirectoryError(
                f"Store path is not a directory: {self.store_path}"
            )

    def _ensure_manifest_file(self):
        """Ensure the manifest file exists in the store directory."""
        if not self.manifest_path.exists():
            self.manifest = StaticManifest(entries={})
            self._save_manifest()

    def _save_manifest(self):
        """Save the manifest file to the store directory."""
        with open(self.manifest_path, "w") as f:
            f.write(self.manifest.serialize())

    def _load_manifest(self):
        """Load the manifest file from the store directory."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest file not found at {self.manifest_path}")

        with open(self.manifest_path) as f:
            return StaticManifest.deserialize(f.read())

    def _ensure_entries_exist(self):
        """Ensure that the file path in each entry points to an existing file."""
        for entry in self.manifest.entries.values():
            self._ensure_linked_file_exists(entry.build_number)

    def _ensure_linked_file_exists(self, build_number: int):
        """Ensure that the file path for the specified entry points to an existing file."""
        entry = self.get_entry(build_number)
        if entry is None:
            raise ValueError(f"No entry found for build number: {build_number}")
        if not Path(entry.file_name).exists():
            raise FileNotFoundError(f"File not found for entry: {entry}")

    def add_entry(self, build_number: int, release_date: str):
        """Add a new entry to the manifest and init the database."""
        file_name = self.file_name_for_new_entry(build_number, release_date)
        if self.get_entry(build_number) is not None:
            raise ValueError(f"Entry already exists for build number: {build_number}")
        if (self.manifest_path / file_name).exists():
            raise FileExistsError(f"File already exists for entry: {file_name}")
        init_database(self.store_path / file_name, init_sql=load_table_definitions())
        self.manifest.entries[build_number] = ManifestEntry(
            build_number=build_number, release_date=release_date, file_name=file_name
        )
        self._save_manifest()

    def get_entry(self, build_number: int | None) -> ManifestEntry | None:
        """Retrieve an entry from the manifest by build number."""
        # return latest build if build_number is None
        if build_number is None:
            if not self.manifest.entries:
                return None
            build_number = max(self.manifest.entries.keys())
        return self.manifest.entries.get(build_number)

    def remove_entry(self, build_number: int):
        """Remove an entry from the manifest by build number and delete the associated database file."""
        if build_number in self.manifest.entries:
            file_name = self.manifest.entries[build_number].file_name
            file_path = self.store_path / file_name
            if file_path.exists():
                file_path.unlink()
            del self.manifest.entries[build_number]
            self._save_manifest()

    def file_name_for_new_entry(self, build_number: int, release_date: str) -> str:
        """Generate a file name for a new entry based on the build number and release date."""
        filename = f"build_{build_number}_{release_date}.sqlite"
        return filename

    def get_file_path_for_entry(self, build_number: int | None) -> Path:
        """Get the full file path for the specified entry based on its file name.

        If build_number is None, the latest build will be used.
        """
        entry = self.get_entry(build_number)
        if entry is None:
            raise ValueError(f"No entry found for build number: {build_number}")
        return self.store_path / entry.file_name
