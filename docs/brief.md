# Brief — Weather-Aware Truck Routing (verbatim)

Build a React (TanStack Router, TanStack React Query, Vite+, bun, ui.aceternity) + Django (SQLite) web app that helps a truck driver choose the safest route based on weather, load weight, and travel time.

## Requirements

The user enters:
- Origin & destination
- Departure date/time
- Load weight

The app should:
- Generate 3 route options using a routing API.
- Sample weather every 10 / 25 / 50 miles, using the truck's estimated arrival time at each checkpoint.
- Calculate weather risk using the provided risk/load rules.
- Recommend the best route, balancing weather risk and travel time.
- Show all routes, checkpoints, risk levels, ETAs, and route summaries on a map.
- Show a weather heatmap along the trip corridor with a 0–48 hour forecast slider.

You may use third-party APIs for routing, geocoding, and weather. You do not need to build a routing engine.

## Risk rules

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | <25 mph | 25–34 | 35–44 | 45–54 | ≥55 mph |
| Rain | <0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow | <0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

Load rules:
- ≥55 mph → No Travel for any load
- 45–54 mph + >30,000 lb → No Travel
- 35–44 mph + >40,000 lb → Severe

## Route recommendation — prefer

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk
4. Shortest travel times

## Deliverables

GitHub repository · Hosted application · 5–10 min Loom walkthrough

## Evaluation

40% routes, weather, risk & recommendation logic · 35% UI, map & heatmap smoothness and performance · 10% code quality · 5% documentation & walkthrough. Prioritize correctness and clarity over extra features.
