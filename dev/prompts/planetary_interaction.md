# Planetary Interaction

This prompt is to support creating code that can determine the unit costs of Planetary Interaction materials under various scenarios.

This prompt should be used to record design decisions and planning.

There is an Excel for the web spreadsheet at `dev/tmp/pi_spreadsheet/PI Planning.xlsx` That has a working implementation of most of the desired data. It is limited by the spreadsheet format, and the challenges of importing data to be used by eve-argus. It can be used for reference, but the display idioms should not be considered examples of the desired data display to be used by eve-argus.

Some objectives are:

- collect the information from the pi doc markdown files at `src/pfmsoft/eve_argus/pi/markdown_docs` and turn it into usable python data models and logic.
- Allow a configurable tax rate for imports and exports. taxes are in important part of calculating unit cost.
- The more complex PI materials can be produced using more than one set of inputs, e.g. P3 from all P1, all P2, or a mix of P1 and P2. Be able to calculate the unit cost of the result material under different scenarios. Some are better to buy, than to make.
- Accept more than one set of materials source price inputs, eg. jita buy, jita sell, jita 10 day average.
- display the results in a way that makes it easy to make production decisions. for instance, if a P3-simple product has the lowest unit cost when a combintaion of P2 an P1 materials are used, clearly display that. Due to the number of possible combinations, this can be complex. Maybe separate tables for `From P1` `From P2` `Mixed P1 P2 Input` with a single top level table that has the best situation?
- Compare unit costs to Jita buy and sell prices to determine profit margin.
- It might be possible to display the whole production tree for a product via html, with pricing aand materials choice displayed.

A later stage will involve finding profitable factory layouts, and determing rate of returns and loadouts. For now, Unit cost calculations are the goal.
