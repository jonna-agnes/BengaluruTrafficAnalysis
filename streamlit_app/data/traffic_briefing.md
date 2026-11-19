# Bengaluru Traffic Briefing
_Generated 2026-11-19 23:17_

## Executive summary
- Silk Board is the worst area: average speed 33.4 km/h, 26.2% of observations High or Severe, and the highest average occupancy (17.9%).
- Weekday congestion peaks sharply at 08:00 (45.9% High/Severe) and 17:00–18:00 (40.9% and 35.8%). Morning peak is hit hardest in Silk Board, ORR, Marathahalli and Hebbal.
- Rain roughly triples the share of High/Severe observations (17.9% vs 5.2% in clear weather), and incidents cut speeds well below the 38.1 km/h network average.
- The ML model forecasts 7 of 20 segments at High or Severe for 09:00 on 7 July, with 4 more marked as improving. Silk Board, Hebbal and Marathahalli remain the priority corridors.

## Hotspots
**Areas (worst first):**
- **Silk Board:** 33.44 km/h avg speed, 17.94% avg occupancy, 26.20% High/Severe, 1.14M vehicles.
- **Hebbal:** 43.53 km/h, 14.56% High/Severe, 1.26M vehicles (highest volume).
- **Marathahalli:** 37.15 km/h, 11.67% High/Severe.
- **Outer Ring Road:** 45.98 km/h, 10.12% High/Severe.

**Worst road segments:**
- **SB-01** Hosur Road at Silk Board Junction: rank 1.88, 33.25 km/h.
- **SB-02** ORR, Silk Board to HSR Layout: rank 1.79, 33.63 km/h.
- **HB-01** Bellary Road at Hebbal Flyover: rank 1.65, 42.90 km/h.
- **HB-02** ORR, Hebbal to Nagawara: rank 1.51, 44.16 km/h.
- **MH-01** ORR at Marathahalli Bridge: rank 1.50, 36.99 km/h.

**Incident-prone roads:** MG Road at Trinity Circle (35 incident observations), Yeshwanthpur Circle (35), Hosur Road at Silk Board Junction (32), Bellary Road at Hebbal Flyover (22).

## Peak hours
- **Weekday peaks:** 08:00 (avg 25.7 km/h, 45.9% High/Severe), 17:00 (26.2 km/h, 40.9%) and 18:00 (26.6 km/h, 35.8%). 16:00 and 09:00 are secondary.
- **Morning peak:** Silk Board, Outer Ring Road, Marathahalli, Hebbal, Whitefield, Yeshwanthpur and Electronic City all peak at 08:00.
- **Evening peak:** Koramangala, Indiranagar and MG Road peak at 18:00. These areas have low High/Severe shares overall (0.13%, 0.03%, 0.83%), so the evening issue is more about speed than severity.
- **Daily pattern:** 4–5 July (weekend) had the best speeds (42.1 and 41.1 km/h) and the lowest High/Severe shares (0.3% and 0.5%). Weekday High/Severe shares ranged from 7.9% to 16.8%, with 1 July the worst day (34.8 km/h, 16.8%).

## Weather & incidents
- **Weather:** Rain reduces average speed to 32.4 km/h and raises High/Severe to 17.9%, compared with 39.3 km/h and 5.2% in clear conditions. Heavy rain averages 32.2 km/h, but its High/Severe share is only 2.1%. This is based on just 472 observations, so treat that figure cautiously.
- **Accidents:** 110 observations, average 16.1 km/h, across 7 segments. These are the most severe slowdowns.
- **Vehicle breakdowns:** 120 observations, average 19.3 km/h, across 12 segments.
- **Waterlogging:** 10 observations, average 22.6 km/h, on 1 segment. Too few to draw a strong conclusion.
- Incidents are sharply below the 38.1 km/h network average, so clearing them quickly has a large effect on speeds.

## Next 30 minutes (ML forecast)
Forecast for 09:00 IST, 7 July:
- **Remain High/Severe:** SB-01 (Severe, confidence 0.954), HB-01 (High, 0.983), HB-02 (High, 0.948), WF-01 (High, 0.829), WF-02 (High, 0.711), YP-02 (High, 0.624), YP-01 (High, 0.539), EC-02 (High, 0.460).
- **Improving, but still High:** MH-01 (Severe to High, 0.965), SB-02 (Severe to High, 0.936), OR-02 (Severe to High, 0.926), OR-01 (Severe to High, 0.855), MH-02 (Severe to High, 0.821).
- **Worsening:** No segment is forecast to worsen. EC-01 falls from High to Moderate.
- **Lower-risk:** KM-01 and KM-02 stay Moderate. MG-01 and MG-02 move from Moderate to Low. IN-01 and IN-02 stay Low.

**Model accuracy:** 86.4% held-out accuracy (macro-F1 0.72), against 82.4% for the persistence baseline. Forecast confidence is lower for YP-01 (0.539), EC-02 (0.460), and YP-02 (0.624), so treat those forecasts with caution.

## Recommended actions
1. **Silk Board signal timing (highest priority):** Extend green phases on Hosur Road and ORR approaches for the 08:00 and 17:00–18:00 peaks. SB-01 and SB-02 stay Severe/High and have the lowest speeds (about 33 km/h). Basis: Silk Board has 26.2% High/Severe and occupancy of 17.9%.
2. **Deploy traffic police at Silk Board, Hebbal and Marathahalli junctions from 07:45 to 09:30 and 16:45 to 18:30:** These are the three areas with the most High/Severe time at the morning peak. Basis: 08:00 is the worst weekday hour in seven areas.
3. **Rain-day protocol:** When rain is forecast, pre-position incident teams on the top incident roads: MG Road at Trinity Circle, Yeshwanthpur Circle, Hosur Road at Silk Board, and Bellary Road at Hebbal Flyover. Basis: rain cuts average speed to 32.4 km/h and raises High/Severe to 17.9%.
4. **Fast incident clearance:** Prioritise accidents (16.1 km/h average) and breakdowns (19.3 km/h) on the affected segments. Basis: incidents are the lowest-speed category in the data.
5. **Diversions for ORR corridors:** Consider diverting through traffic away from SB-02 and MH-01 toward alternative routes during the 08:00 peak. Confirm available alternatives on the ground first, since the context does not include a diversion network. Basis: both segments are forecast High at 09:00.
6. **Commuter advisories:** Issue alerts for Silk Board, Hebbal, Marathahalli, Whitefield and Yeshwanthpur ahead of the 08:00 and 17:00 peaks, and for Koramangala, Indiranagar and MG Road ahead of 18:00. Basis: the forecast and peak-hour tables above.

*Note: This briefing is based on synthetic simulator data for Bengaluru (not real sensor readings). Actual road conditions were not available in the provided context and are not assessed here.*
