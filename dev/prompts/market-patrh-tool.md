# Market Path Tool Prompt

I want to implement downloading market groups in html and javascript. The html file should be self contained.

First we will have to get the market group ids from the Eve Online ESI, then download each market group. I would like the market group downloads to happen in parallel, for better speed.

After all the data has been downloaded, combine it into a JSON object with
`received_at`, `expires_at`, and `market_groups` keyed by market group ID.

create the market groups tool in the dev/tools folder, and keep the look consistent with the other tools.

### Market groups tool

Open [the market groups tool](../tools/market-groups.html) directly in a modern
browser. Load a raw OpenAPI schema or a dereferenced, timestamped schema file,
or fetch the latest schema from ESI. A valid schema is required; its
compatibility date and market-group operations determine the requests.

Choose a language (English, `en`, by default) and select **Fetch market
groups** to fetch the ID list and then details with at most ten concurrent
requests. The selection applies to the next fetch and does not change an
already loaded dataset or its save filename. There is no time-based rate limit or automatic
retry. The page shows progress and displays the completed JSON; select **Save
JSON** to download it as `market-groups-LANGUAGE-YYYY-MM-DD.json`, using the
language selected for that fetch and the current UTC date at save time. Any
failed request stops the run and prevents partial export.
Errors, including rate-limit responses, are shown; retrying starts a new run.
Calls request names in the selected language and do not require login.

The output contains `received_at` (when the last response was received),
`expires_at` (the ID-list response's expiry, or `null` if unavailable), and
`market_groups`, keyed by ID. Records contain `market_group_id`, `description`,
`int_path`, `name`, `parent_group_id`, `str_path`, and `types`. Paths include the
root and the group itself. ESI does not provide `icon_id` or `has_types`, so
those fields are omitted. ESI type lists may differ from static data exports, and
the responses are not an atomic snapshot. Missing parents and cycles fail
explicitly. Run the focused tests with
`node --test dev/tools/tests/test_market_groups.js`.

### GetMarketsGroupsMarketGroupId

#### Summary

| Field                  | Value                             |
| ---------------------- | --------------------------------- |
| Operation ID           | GetMarketsGroupsMarketGroupId     |
| Method                 | GET                               |
| Path                   | /markets/groups/{market_group_id} |
| Authorization Required | No                                |
| Compatibility Date     | 2020-01-01                        |
| Response Keys          | 200, default                      |
| Summary                | Get item group information        |

#### Description

Get information on an item group This route expires daily at 11:05

#### Parameters

| Name                 | In     | Required | Type    | Description                                                                                                            |
| -------------------- | ------ | -------- | ------- | ---------------------------------------------------------------------------------------------------------------------- |
| market_group_id      | path   | Yes      | integer | An Eve item group ID                                                                                                   |
| Accept-Language      | header | No       | string  | The language to use for the response.                                                                                  |
| If-None-Match        | header | No       | string  | The ETag of the previous request. A 304 will be returned if this matches the current ETag.                             |
| X-Compatibility-Date | header | Yes      | string  | The compatibility date for the request.                                                                                |
| X-Tenant             | header | No       | string  | The tenant ID for the request.                                                                                         |
| If-Modified-Since    | header | No       | string  | The date the resource was last modified. A 304 will be returned if the resource has not been modified since this date. |

#### Parameters Schema

```json
[
  {
    "in": "path",
    "name": "market_group_id",
    "required": true,
    "schema": {
      "description": "An Eve item group ID",
      "format": "int64",
      "type": "integer"
    }
  },
  {
    "description": "The language to use for the response.",
    "in": "header",
    "name": "Accept-Language",
    "schema": {
      "default": "en",
      "enum": ["en", "de", "fr", "ja", "ru", "zh", "ko", "es"],
      "type": "string"
    }
  },
  {
    "description": "The ETag of the previous request. A 304 will be returned if this matches the current ETag.",
    "in": "header",
    "name": "If-None-Match",
    "schema": {
      "type": "string"
    }
  },
  {
    "description": "The compatibility date for the request.",
    "in": "header",
    "name": "X-Compatibility-Date",
    "required": true,
    "schema": {
      "enum": ["2026-08-04"],
      "format": "date",
      "type": "string"
    }
  },
  {
    "description": "The tenant ID for the request.",
    "example": "",
    "in": "header",
    "name": "X-Tenant",
    "schema": {
      "default": "tranquility",
      "type": "string"
    }
  },
  {
    "description": "The date the resource was last modified. A 304 will be returned if the resource has not been modified since this date.",
    "in": "header",
    "name": "If-Modified-Since",
    "schema": {
      "type": "string"
    }
  }
]
```

#### Request Body (json_payload) Schema

No Request Body Schema.

#### Response Schema

```json
{
  "properties": {
    "description": {
      "type": "string"
    },
    "market_group_id": {
      "format": "int64",
      "type": "integer"
    },
    "name": {
      "type": "string"
    },
    "parent_group_id": {
      "format": "int64",
      "type": "integer"
    },
    "types": {
      "items": {
        "description": "type integer",
        "format": "int64",
        "type": "integer"
      },
      "type": "array"
    }
  },
  "required": ["market_group_id", "name", "description", "types"],
  "type": "object"
}
```

#### Extensions

```json
{
  "x-compatibility-date": "2020-01-01"
}
```

```python
@dataclass(slots=True, kw_only=True)
class MarketGroupsRecord:
    market_group_id: int
    description: str
    has_types: bool
    icon_id: int | None
    int_path: tuple[int, ...]
    name: str
    parent_group_id: int | None
    str_path: tuple[str, ...]
    types: tuple[int, ...]

    def int_path_str(self, sep: str = "/") -> str:
        """Converts the integer path of a market group to a string representation.

        Args:
            sep: The separator to use between path elements. Defaults to "/".

        Returns:
            A string representation of the market group's integer path.
        """
        return sep.join(str(i) for i in self.int_path)

    def str_path_str(self, sep: str = "/") -> str:
        """Converts the string path of a market group to a single string representation.

        Args:
            sep: The separator to use between path elements. Defaults to "/".

        Returns:
            A string representation of the market group's string path.
        """
        return sep.join(self.str_path)
```

First, we might need to develop the Eve Esi Schema tool. It should also live in one local file in dev/tools.

Features:

- display valid compatibility dates
- display schema changelog
- display selected schema
- save all of the above to files.

```python
# ESI API URLs
COMPATIBILITY_DATES_URL = "https://esi.evetech.net/meta/compatibility-dates"
"""URL to fetch the list of compatibility dates from the ESI API."""
ESI_SCHEMA_URL = "https://esi.evetech.net/meta/openapi.json"
"""URL to fetch ESI OpenAPI schema."""
ESI_SCHEMA_CHANGELOG_URL = "https://esi.evetech.net/meta/changelog"
"""URL to fetch ESI schema changelog."""
```

### Schema browser

Open [the schema browser](../tools/esi-schema.html) directly in a modern browser.
Fetching from ESI requires internet access and cross-origin access to ESI; importing
local files does not. Use **Fetch compatibility dates** in the Compatibility
dates pane at the top, select a date in ESI data, and fetch its schema. Save dates
from the same pane. Fetch and save the changelog separately from the Schema
changelog pane beside it. Metadata filenames include their latest date, using
the date-keyed changelog or ESI's `changelog` wrapper. If no date is available
or a changelog key is invalid, the filename has no date and a warning is shown.

Open a raw OpenAPI JSON file or an eve-link `dereferenced_schema`/`timestamp`
file. The page displays formatted JSON next to operations grouped by tag; the
panes stack on narrow screens. The display
defaults to the dereferenced schema; use the **Display schema as** radio buttons
to switch between dereferenced and raw views when both are available. The
selected operation stays visible when switching views, if available in both.
Select **Show full schema** to return. If conversion fails, the raw view remains
available and the error is displayed. Save the raw
schema when available or save a dereferenced, timestamped envelope. Raw file
imports have an unknown (`null`) receipt timestamp; a dereferenced file cannot
recover its original raw schema. Saved schema filenames include the compatibility
date from the loaded schema's `info.version`. If it is missing or invalid, the
file is saved without a date and a warning is shown. Conversion supports
internal JSON pointers and reports external, missing, and cyclic references as
errors. Unlike eve-link's current resolver, it preserves sibling fields on a
reference.

The page does not store data between reloads. Run the focused JavaScript tests
with `node --test dev/tools/tests/test_esi_schema_browser.js`.
