# Bengaluru Traffic Briefing
_Generated 2026-11-19 22:16_

## Executive summary
- Congestion is concentrated, not city-wide: 72.2% of observations are Low, but Silk Board alone has 25.97% High/Severe, and the top 5 segments are all in Silk Board, Hebbal, or Marathahalli/ORR.
- Weekday morning peak at 08:00 is the worst hour (45.9% High/Severe, 25.7 km/h); evening peak at 17:00–18:00 follows.
- Rain sharply raises High/Severe share (17.9% in Rain vs 5.2% Clear), and accidents and breakdowns cut speeds to about 23 km/h.
- The ML forecast shows 9 of 20 segments at High/Severe for the 09:00 slot on 2026-07-07, with 3 expected to improve from Severe. Model accuracy is 86.7% vs 82.4% for persistence.

## Hotspots
- **Silk Board** is the worst area: 33.48 km/h average speed, 17.85% average occupancy, 25.97% High/Severe, and 1,140,496 vehicles.
  - SB-01 (Hosur Road at Silk Board Junction): rank 1.88, 33.26 km/h.
  - SB-02 (ORR, Silk Board to HSR Layout): rank 1.78, 33.70 km/h.
- **Hebbal** has the highest volume (1,262,176 vehicles) and 14.31% High/Severe.
  - HB-01 (Bellary Road at Hebbal Flyover): rank 1.65, 43.01 km/h.
  - HB-02 (ORR, Hebbal to Nagawara): rank 1.51, 44.16 km/h.
- **Marathahalli** has 11.67% High/Severe; MH-01 (ORR at Marathahalli Bridge) is rank 1.49 at 37.07 km/h.
- **Outer Ring Road** has 10.07% High/Severe despite the highest area average speed (46.03 km/h), so its congestion is episodic rather than sustained.
- **MG Road** and **Indiranagar** have the lowest speeds (28.77 and 31.74 km/h) but almost no High/Severe time (0.75% and 0.00%), so they are slow but not jammed.

## Peak hours
- Weekday peaks: 08:00 (45.9% High/Severe), 17:00 (40.9%), and 18:00 (35.6%). The 16:00 and 09:00 hours also elevated.
- Morning peak (08:00) is worst in Silk Board, ORR, Marathahalli, Hebbal, Whitefield, Yeshwanthpur, and Electronic City.
- Evening (18:00) is worst in Koramangala, Indiranagar, and MG Road.

## Weather & incidents
- **Rain:** average speed falls to 32.4 km/h and High/Severe rises to 17.9% (vs 5.2% in Clear and 8.1% in Cloudy).
- **Heavy rain:** avg speed 32.6 km/h, but 0.0% High/Severe across 472 observations. The sample is small, so treat this with caution.
- **Accidents:** 110 observations, average 22.8 km/h, across 7 segments.
- **Vehicle breakdowns:** 120 observations, average 22.7 km/h, across 12 segments.
- **Waterlogging:** 10 observations, average 41.1 km/h, affecting 1 segment; not a speed-reducing event in this data.
- **Incident hotspots:** MG Road at Trinity Circle (35) and Yeshwanthpur Circle (35) lead, followed by Hosur Road at Silk Board Junction (32) and Bellary Road at Hebbal Flyover (22).
- Daily trend: 1–3 July were the worst days (16.8% High/Severe on 1 July); 4–5 July were calmest (0.3–0.5%).

## Next 30 minutes (ML forecast)
Forecast for 2026-07-07 09:00 IST:
- **Remain/become High or Severe:** SB-01 (Severe, stable), HB-01 and HB-02 (High, stable), WF-02, YP-02, WF-01, YP-01, EC-02 (High, stable), and MH-02, OR-01, OR-02, SB-02, MH-01 (Severe now, forecast High, improving).
- **Worsening:** IN-02 (CMH Road, Indiranagar), from Low to Moderate (confidence 0.562, low).
- **Improving:** EC-01 (High to Moderate) and MG-02 (Moderate to Low).
- Model accuracy is 86.7% (macro-F1 0.71), against 82.4% for the persistence baseline. Several confidence scores are below 0.6 (EC-02, YP-01, IN-02, KM-02, MG-01 range 0.556–0.599), so treat those forecasts as less certain.

## Recommended actions
1. **Silk Board signal retiming (highest priority):** prioritise the 08:00 and 17:00 peaks at SB-01 and SB-02, and monitor the Severe-to-High easing on SB-02 before reducing green time on cross-streets.
2. **Deploy traffic police to Silk Board Junction and Hebbal Flyover (Bellary Road)** before 08:00 and 17:00, where incidents and High/Severe shares are highest.
3. **Pre-position response for Yeshwanthpur Circle and MG Road at Trinity Circle:** these have the most incident observations (35 each), so clear breakdowns quickly.
4. **Rain-day protocol:** when rain is forecast, trigger wider signal coordination and diversion advisories for Silk Board and Marathahalli, since High/Severe share rises about 3x in rain.
5. **Commuter advisories:** warn of 08:00–09:00 and 17:00–18:30 congestion on the Silk Board, Hebbal, and Marathahalli/ORR corridors; suggest alternative routes or earlier departures.
6. **Monitor IN-02 and the Whitefield/Yeshwanthpur High forecasts:** these are low-confidence or newly worsening and need a quick re-check at the next forecast cycle rather than immediate deployment.

*Note: this briefing uses synthetic simulator data for Bengaluru, not real sensor readings.*
