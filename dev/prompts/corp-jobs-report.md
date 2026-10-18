# Corporation jobs report

    Note there is code for an old non-working implementation of this report at

    - src/pfmsoft/eve_argus/reports/old/corp_industry_jobs_markdown.py
    - src/pfmsoft/eve_argus/reports/old/corp_industry_jobs.py
    - src/pfmsoft/eve_argus/templates/corp_industry_jobs
    - output examples at dev/proof-scripts/proof-output/esi-data-loader/corporation_industry_jobs*

    This is provided for reference, but may not provide all the desire new features. This code will be removed after new implementation is complete. Do not attempt to force the new implementation to fit the old code.

I want to implement a report for Corporation jobs.

The jobs are found in the dynamic database, and can be accessed via src/pfmsoft/eve_argus/dynamic/read.py

static data can be accesed by src/pfmsoft/eve_argus/static/read.py

The most current set of jobs should be used, and the received_at and expires_at information should be included in the markdown version of the report.

The public report function should take data arguments, accessing databases is outside the scope of the report.

## Required data

- Corporation jobs from the dynamic database
- types dataset from the static database
- market groups dataset from the static database
- industry_activities from the static dataset
- EsiLink and EsiSchema to allow name dereferencing.

## Data collection

id fields in the job records need to be dereferenced into names. Some of these are available from the static database types dataset, but others are more easily gotten from the src/pfmsoft/eve_argus/esi/fetch.universe_names. one or two will cause universe names to error. when we figure out which ones these are, they will be excluded, and we should note them in the docstring for the dynamic database model. Collect all valid ids, then make the universe_names call.

We should also include the market path for the blueprint. this can be found by getting the market group from static->types and getting the path from static->market-groups.

Use a dataclass to hold the collected data.

## Outputs

- A json file of the collected, dereferenced data.
- A csv file of same
- A markdown report of same.

Use jinja templates to generate the markdown version of the report.
templates are collected in src/pfmsoft/eve_argus/templates

## Flow

I envision one function that collects the required data. Then other functions that output that collected data into various formats.
