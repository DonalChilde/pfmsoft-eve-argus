"""Top-level package for Eve Argus ESI fetch operations.

This package contains functionality for fetching ESI data and updating the appropriate
database accordingly.

For functions that update the dynamic database:
 - The database will be check for existing data.
 - If existing data is found and it is not expired, updates will be skipped.
 - If existing data is not found or is expired, updates will be performed.
 - A results object will be returned indicating the outcome of the update operations.
"""
