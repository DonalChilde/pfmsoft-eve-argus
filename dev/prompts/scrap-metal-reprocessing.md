# Reprocessing deal finder

NOTE: The initial efforts will be to generate scripts in the dev/proof-scripts/reprocessing directory. once a final path has been determined, the code will be moved into eve-argus proper. dev/proof-scripts/proof-output/reprocessing can be used for output.

In Eve Online it is possible to reprocess ships and equipment and regain a portion of the materials used to create the item.

There is only one skill that affects reprocessing non-ore/gas/ice items, and the maximum percentage of materials regained is 55%, rounded down.

Eve-argus has access to enough information to make reports on the precrocessed value of items, and the market values of both the item, and its reprocessed materials.

Note, portion size determines the number of items required to reprocess one unit, eg a frigates portion size is one, and a typical ammo portion size is 100. 100 units of that ammo would be required in order to reprocess it.

The materials contained in items are defined in type_materials. Not all items in this table might be published, or available in the market.

It is assumed that the type_materials entry represents a portion size of items, eg. 100 ammo, but this needs to be verified in game.

Goals:

- Find ways to make reprocessing profitable
- make a markdown document that details the reprocessed materials available from an item, the market price buy/sell at various hubs of the item and its constituent materials, grouped by market path. I envision a table of the various data for each item.
- in another document
  - Find deals on reprocessed goods, where either the buy. sell, or both price of the items is less thatn the value of the reprocessed materials.
  - Find deals or improved deals that generate profit buy moveing those reprocessable goods between market hubs.

Document types and tools available:

- markdown
- html
- spreadsheets that can import csv for further processing.
