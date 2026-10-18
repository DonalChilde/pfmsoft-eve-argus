# Eve Argus Overview

This is an overview of the current and planned functionality of the Eve Argus app.
It covers the CLI interface, the public api, and datastorage locations.
This document should be kept current as the program changes.

## CLI

    /src/pfmsoft/eve_argus/cli

As a primarily cli driven program, the cli is the most common entrypoint for the user. In the future, a gui might be added, either through TKinter/NiceGui or a more web based html server based around htmx 4.

### Fetch

    /src/pfmsoft/eve_argus/cli/fetch

Commands for fetching data from the Eve Online ESI

### Reports

    /src/pfmsoft/eve_argus/cli/reports

Commands for reporting on argus data, e.g. corporation jobs, blueprints.

### Static

    /src/pfmsoft/eve_argus/cli/static

Commands for working with Eve static data, e.g. downloading and importing.

### Dynamic

    /src/pfmsoft/eve_argus/cli/dynamic

Commands for working with the dynamic database, e.g. purge old data, list current datasets.

### Util

    /src/pfmsoft/eve_argus/cli/util

Misc commands, and access to the cli for sub-apps. esd, eve-link, eve-auth.

- name-lookup - Lookup ids for names. Can accept more than one name per request.

## Components

Major subsystems of the Argus app.

### Settings

    /src/pfmsoft/settings.py

Provides a single source for runtime application settings. Can be used as a simple way to instance required Argus objects. An application directory can be loaded from environment settings, and user selectable settings can be loaded from a TOML file located in that app directory.

### Application Data - Not Yet Implemented

Provides a storage location for some persistent application data. e.g. the currently used esi schema version, and static database build number.

### Static Data

    /src/pfmsoft/eve_argus/static

The static data database is a set of data imported from the EVE Online SDE. Only the datasets
expected to be of use to eve-argus have been imported. The datasets are localized to one language
to save space.

### Dynamic data

Provides storage and access to data downloaded from the EVE Esi. This data is ephemeral, and the entire database can be reset with minimal impact on the rest of the program. api datasets may be retained until specifically deleted. e.g each market order call is kept, even when only the most recent is used. Old data should be purged on a regular basis. Some derived datasets only use the latest data, and have only one current version.

### Market History - Not complete.

Provides storage and access to the market history for regions and type_ids. This dataset is split off into its own thing due to the cost of updating the data. each region_id/type_id is a network call, and there could be 10k plus calls per region per day for a full update.

### Templates

    /src/pfmsoft/eve_argus/templates

Provides a central location for jinja templates used to create various objects, e.g. markdown reports.

### esi

    /src/pfmsoft/eve_argus/esi

Contains code related to downloading and validating data from the EVE Online Esi endpoints.

### fetch_esi

    /src/pfmsoft/eve_argus/fetch_esi

Behavior to manage downloading from the ESI only when the currnet data has expired.

### esd

    /src/pfmsoft/eve_argus/esd

Contains cose related to validating and importing data from the EVE Online SDE.

### Reports

    /src/pfmsoft/eve_argus/reports

Contains code to generate reports, e.g. owned corporation blueprints.

### Managed Resources

    /src/pfmsoft/eve_argus/eve_argus.py

the EveArgusResources object manages resource lifecycle.
