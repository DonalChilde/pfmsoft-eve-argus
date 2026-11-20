# PI Factory Planet layouts

At CC Elite, one planet can support:

- 24 or 25 advanced factories and one landing pad
- 24 advanced and 1 High Tech factory and one landing pad
- 2 sets of 12 advanced factories and one landing pad
- 4 sets of 5 advanced factories and one landing pad
- 3 sets of 7 advanced factories and one landing pad

A loadout's goal is to show the max materials that will fit in one launch pad load (10000 m3) that will result in complete use of the inputs.

Some Definitions:

- P3-Complex - P3 that consists of 3 different P2 inputs, or 6 P1 inputs
- P3-Simple - P3 that constists of 2 different P2 inputs, or 4 P1 inputs.
- P4-Low - P4 that consist of 2 P3-Simple inputs, and a P1
- P4-Medium - P4 that consist of 3 P3-Simple inputs
- P4-High - P4 that consist of 3 P3-Complex inputs

## m3 per cycle, cycles per 10000m3

### P1-P2

40 P1 x 2
15.2 m3 per cycle
657 cycles per 10000 m3

### P1-P3-Simple

80 P1 X 4
60.8 m3 per cycle
164 cycles per 10000 m3

### P1-P3-Simple with 2 extra

80 P1 X 4 + 40 P1 x 2
60.8 + 15.2 = 76 m3 per cycle
131 cycles per 10000 m3

### P1-P3-Complex

80 P1 x 6
91.2 m3 per cycle
109 cycles per 10000 m3

### P1-P3-Both

P3-Complex
80 P1 x 6
91.2 m3 per cycle

P3-Simple
80 P1 X 4
60.8 m3 per cycle

Both
91.2 + 60.8 = 152 m3 per cycle
65 cycles per 10000 m3

### P1-P4-Low

160 P1 x 8 + 40 P1
250.8 m3 per cycle
39 cycles per 10000 m3

### P1-P4-Medium

160 P1 x 12
364.8 m3 per cycle
27 cycles per 10000 m3

### P1-P4-High

160 P1 x 18
547.2 m3 per cycle
18 cycles per 10000 m3

### P2-P3-Simple

10 P2 x 2
15 m3 per cycle
666 cycles per 10000 m3

### P2-P3-Complex

10 P2 x 3
22.5 m3 per cycle
444 cycles per 10000 m3

### P2-P4-Low

20 P2 x 4 + 40 P1
60 m3 + 7.6 m3 = 67.6 m3 per cycle
148 cycles per 10000 m3

### P2-P4-Medium

20 P2 x 6
90 m3 per cycle
111 cycles per 10000 m3

### P2-P4-High

20 P2 x 9
135 m3 per cycle
74 cycles per 10000 m3

### P1-P2-P3-Simple-Buy-1-Build-1

80 P1 x 2 + 10 P2
30.4 + 7.5 = 37.9 m3 per cycle
263 cycles per 10000 m3

### P1-P2-P3-Complex-Buy-2-Build-1

80 P1 x 2 + 10 P2 x 2
30.4 + 15 = 45.4 m3 per cycle
220 cycles per 10000 m3

### P1-P2-P3-Complex-Buy-1-Build-2

80 P1 x 4 + 10 P2
60.8 + 7.5 = 68.3 m3 per cycle
146 cycles per 10000 m3

### P1-P2-P4-Medium-Buy-2-Build-4

160 P1 x 8 + 20 P2 x 2
243.2 + 30 = 273.2 m3 per cycle
36 cycles per 10000 m3

### P1-P2-P4-High-Buy-5-Build-4

160 P1 x 8 + 20 P2 x 5
243.2 + 75 = 318.2 m3 per cycle
31 cycles per 10000 m3

## Generic Loadouts

### P1-P2, 24 factories. 27 hour run time. 9849.6 m3 in, 2430 m3 out, 3240 units out.

24 P2 lines.

| Name | Quantity |
| ---- | -------- |
| P1   | 25920    |
| P1   | 25920    |

### P1-P2, 12 factories. 54 hour run time. 9849.6 m3 in, 2430 m3 out, 3240 units out.

12 P2 Lines.

| Name | Quantity |
| ---- | -------- |
| P1   | 25920    |
| P1   | 25920    |

### P1-P3-Simple, 25 factories. 32 hour run time. 9728 m3 in, 1440 m3 out, 480 units out.

5 P3 lines + 20 P2 Lines

| Name | Quantity |
| ---- | -------- |
| P1   | 12800    |
| P1   | 12800    |
| P1   | 12800    |
| P1   | 12800    |

### P1-P3-Simple, 12 factories. 82 hour run time. 9971.2 in, 1476 m3 out, 492 units out.

2 P3 lines + 8 P2 Lines + 2 extra.
Consider using other capacity for contrasting p2 production.

| Name | Quantity |
| ---- | -------- |
| P1   | 13120    |
| P1   | 13120    |
| P1   | 13120    |
| P1   | 13120    |

### P1-P3-Simple with extra, 12 factories. 65 hour run time. 9986.4 in, 2197.5 m3 out, 390/1370 units out.

2 P3 lines + 8 P2 Lines + 2 P2

| Name | Quantity |
| ---- | -------- |
| P1   | 10400    |
| P1   | 10400    |
| P1   | 10400    |
| P1   | 10400    |
| P1   | 5480     |
| P1   | 5480     |

### P1-P3-Simple, 5 factories. 164 hour run time. 9971.2 in, 1476 m3 out, 492 units out.

1 P3 Line + 4 P2 lines.
Can fit 4 on one planet

| Name | Quantity |
| ---- | -------- |
| P1   | 13120    |
| P1   | 13120    |
| P1   | 13120    |
| P1   | 13120    |

### P1-P3-Complex, 12 factories. 109 hour run time. 9940.8 m3 in, 109 m3 out, 327 units out.

1 P3 Line + 6 P2 Lines + 5 Extra

| Name | Quantity |
| ---- | -------- |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |

### P1-P3-Complex, 7 factories. 109 hour run time. 9940.8 m3 in, 109 m3 out, 327 units out.

1 P3 Line + 6 P2 Lines.
Can fit 3 on one planet.

| Name | Quantity |
| ---- | -------- |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |
| P1   | 8720     |

### P1-P3-Both, 12 factories. 65 hour run time. 9880 m3 in, 1170 m3 out, 390/390 units out.

1 P3 Line + 6 P2 Lines.
1 P3 Line + 4 P2 lines.

| Name | Quantity |
| ---- | -------- |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |
| P1   | 5200     |

### P1-P3-Complex, 21 factories. 36 hour run time. 9849.6 m3 in, 972 m3 out, 324 units out.

3 P3 lines + 18 P2 lines.

| Name | Quantity |
| ---- | -------- |
| P1   | 8640     |
| P1   | 8640     |
| P1   | 8640     |
| P1   | 8640     |
| P1   | 8640     |
| P1   | 8640     |

### P1-P4-Low, 20+1 factories. 39 hour run time. 9781.2 m3 in, 1950 m3 out, 39 units out.

4 P3 lines, 16 P2 lines, 1 High Tech Line
1 unit per hour

| Name | Quantity |
| ---- | -------- |
| P1   | 6240     |
| P1   | 6240     |
| P1   | 6240     |
| P1   | 6240     |
| P1   | 6240     |
| P1   | 6240     |
| P1   | 6240     |
| P1   | 6240     |
| P1   | 1560     |

### P1-P4-Medium, 15+1 factories. 54 hour run time. 9849.6 m3 in, 1350 m3 out, 27 units out.

3 P3 lines, 12 P2 lines, 1 High Tech line
1 unit per 2 hours

| Name | Quantity |
| ---- | -------- |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |
| P1   | 4320     |

### P1-P4-High, 21+1 factories. 36 hour run time. 9849.6 m3 in, 900 m3 out, 18 units out.

3 P3 lines, 18 P2 lines, 1 High Tech line
1 unit per 2 hours

| Name | Quantity |
| ---- | -------- |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |
| P1   | 2880     |

### P2-P3-Complex, 24 factories. 18 hour run time. 9720 m3 in, 3888 m3 out, 1296 units out.

24 P3 lines

| Name | Quantity |
| ---- | -------- |
| P2   | 4320     |
| P2   | 4320     |
| P2   | 4320     |

### P2-P3-Complex, 12 factories. 36 hour run time. 9720 m3 in, 3888 m3 out, 1296 units out.

12 P3 Lines

| Name | Quantity |
| ---- | -------- |
| P2   | 4320     |
| P2   | 4320     |
| P2   | 4320     |

### P2-P3-Simple, 24 factories. 27 hour run time. 9720 m3 in, 5832 m3 out, 1944 units out.

24 P3 Lines

| Name | Quantity |
| ---- | -------- |
| P2   | 6480     |
| P2   | 6480     |

### P2-P3-Simple, 12 factories. 54 hour run time. 9720 m3 in, 5832 m3 out, 1944 units out.

12 P3 lines.

| Name | Quantity |
| ---- | -------- |
| P2   | 6480     |
| P2   | 6480     |

### P2-P4-Low, 20+5 factories. 29 hour run time. 9802 m3 in, 7250 m3 out, 145 units out.

20 P3 lines, 5 High Tech lines
5 units per hour.

| Name | Quantity |
| ---- | -------- |
| P2   | 2900     |
| P2   | 2900     |
| P2   | 2900     |
| P2   | 2900     |
| P1   | 5800     |

### P2-P4-Medium, 18+3 factories. 37 hour run time. 9990 m3 in, 5550 m3 out, 111 units out.

| Name | Quantity |
| ---- | -------- |
| P2   | 2220     |
| P2   | 2220     |
| P2   | 2220     |
| P2   | 2220     |
| P2   | 2220     |
| P2   | 2220     |

### P2-P4-High, 18+3 factories. 24 hour run time. 9720 m3 in, 3600 m3 out, 72 units out.

| Name | Quantity |
| ---- | -------- |
| P2   | 1440     |
| P2   | 1440     |
| P2   | 1440     |
| P2   | 1440     |
| P2   | 1440     |
| P2   | 1440     |
| P2   | 1440     |
| P2   | 1440     |
| P2   | 1440     |

### P2-P4-Low, 8+2 factories. 73 hour run time. 9869.6 m3 in, 7300 m3 out, 146 units out.

2 lines, 2 units per hour of the same P4 product. Each of the 2 P3 inputs is supplied by 4 Advanced Industry factories.

| Name | Quantity |
| ---- | -------- |
| P2   | 2920     |
| P2   | 2920     |
| P2   | 2920     |
| P2   | 2920     |
| P1   | 5840     |

One planet can hold one 8+2 setup and one 12+2 setup, each with its own launch pad. The loads and run times are per setup.

### P2-P4-Medium, 12+2 factories. 55 hour run time. 9900 m3 in, 5500 m3 out, 110 units out.

2 lines, 2 units per hour of the same P4 product. Each of the 3 P3 inputs is supplied by 4 Advanced Industry factories.

| Name | Quantity |
| ---- | -------- |
| P2   | 2200     |
| P2   | 2200     |
| P2   | 2200     |
| P2   | 2200     |
| P2   | 2200     |
| P2   | 2200     |

One planet can hold one 8+2 setup and one 12+2 setup, each with its own launch pad. The loads and run times are per setup.

### P2-P4-High, 12+2 factories. 37 hour run time. 9990 m3 in, 3700 m3 out, 74 units out.

2 lines, 2 units per hour of the same P4 product. Each of the 3 P3 inputs is supplied by 4 Advanced Industry factories.

| Name | Quantity |
| ---- | -------- |
| P2   | 1480     |
| P2   | 1480     |
| P2   | 1480     |
| P2   | 1480     |
| P2   | 1480     |
| P2   | 1480     |
| P2   | 1480     |
| P2   | 1480     |
| P2   | 1480     |

One planet can hold one 8+2 setup and one 12+2 setup, each with its own launch pad. The loads and run times are per setup.

### P3-P4-Low, 2 factories. 99 hour run time. 8632.8 m3 in, 9900 m3 out, 198 units out.

| Name | Quantity |
| ---- | -------- |
| P3   | 1188     |
| P3   | 1188     |
| P1   | 7920     |

One Launchpad per 2 High Tech Factories, can place 4 of these pair on one planet.

### P3-P4-Medium-or-High, 2 factories. 92 hour run time. 9936 m3 in, 9200 m3 out, 184 units out.

| Name | Quantity |
| ---- | -------- |
| P3   | 1104     |
| P3   | 1104     |
| P3   | 1104     |

One Launchpad per 2 High Tech Factories, can place 4 of these pair on one planet.

## Split build loadouts

### P1-P3-Simple-Buy-1-Build-1, 24 factories. 32 hour run time. 9702.4 m3 in, 2304 m3 out, 768 units out.

Split buy and build, 8 lines

| Name | Quantity |
| ---- | -------- |
| P1   | 20480    |
| P1   | 20480    |
| P2   | 2560     |

### P1-P3-Simple-Buy-1-Build-1, 12 factories. 65 hour run time. 9854 m3 in, 2340 m3 out, 780 units out.

4 P3 + 8 P2

| Name | Quantity |
| ---- | -------- |
| P1   | 20800    |
| P1   | 20800    |
| P2   | 2600     |

### P1-P3-Simple-Buy-1-Build-1, 5 factories

1 P3 + 2 P2 + 2 extra

### P1-P3-Complex-Buy-2-Build-1, 24 factories. 27 hour run time. 9806.4 m3 in, 1944 m3 out, 648 units out.

8 P3 + 16 P2

| Name | Quantity |
| ---- | -------- |
| P1   | 17280    |
| P1   | 17280    |
| P2   | 2160     |
| P2   | 2160     |

### P1-P3-Complex-Buy-2-Build-1, 12 factories. 55 hour run time. 9988 m3 in, 1980 m3 out, 660 units out.

4 P3 + 8 P2

| Name | Quantity |
| ---- | -------- |
| P1   | 17600    |
| P1   | 17600    |
| P2   | 2200     |
| P2   | 2200     |

### P1-P3-Complex-Buy-2-Build-1, 5 factories.

1 P3 + 2 P2 + 2 extra

### P1-P3-Complex-Buy-1-Build-2, 25 factories. 29 hour run time. 9903.5 m3 in, 1305 m3 out, 435 units out.

5 P3 + 20 P2

| Name | Quantity |
| ---- | -------- |
| P1   | 11600    |
| P1   | 11600    |
| P1   | 11600    |
| P1   | 11600    |
| P2   | 1450     |

### P1-P3-Complex-Buy-1-Build-2, 12 factories. 146 hour run time. 9971.8.5 m3 in, 1314 m3 out, 438 units out.

2 P3 + 8 P2 + 2 extra

| Name | Quantity |
| ---- | -------- |
| P1   | 11680    |
| P1   | 11680    |
| P1   | 11680    |
| P1   | 11680    |
| P2   | 1460     |

### P1-P3-Complex-Buy-1-Build-2, 5 factories.

1 P3 + 4 P2

### P1-P4-Medium-Buy-2-Build-4, 22+1 factories. 36 hour run time. 9835.2 m3 in, 1800 m3 out, 36 units out.

1 line, 1 unit per hour. Build 4 P2 inputs from P1, buy 2 P2 inputs.

| Name | Quantity |
| ---- | -------- |
| P1   | 5760     |
| P1   | 5760     |
| P1   | 5760     |
| P1   | 5760     |
| P1   | 5760     |
| P1   | 5760     |
| P1   | 5760     |
| P1   | 5760     |
| P2   | 720      |
| P2   | 720      |

### P1-P4-High-Buy-5-Build-4, 22+1 factories. 31 hour run time. 9864.2 m3 in, 1550 m3 out, 31 units out.

1 line, 1 unit per hour. Build 4 P2 inputs from P1, buy 5 P2 inputs.

| Name | Quantity |
| ---- | -------- |
| P1   | 4960     |
| P1   | 4960     |
| P1   | 4960     |
| P1   | 4960     |
| P1   | 4960     |
| P1   | 4960     |
| P1   | 4960     |
| P1   | 4960     |
| P2   | 620      |
| P2   | 620      |
| P2   | 620      |
| P2   | 620      |
| P2   | 620      |
