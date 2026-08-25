"""Parameterized Cypher used by the API, seed script, and forecast engine.

Every query takes parameters via the official Neo4j driver — never string concatenation.
"""

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

CREATE_USER = """
CREATE (u:User {
  email: $email,
  password_hash: $password_hash,
  verified: false,
  is_verified: false,
  name: $name,
  created_at: $created_at
})
RETURN u.email AS email, u.verified AS verified, u.name AS name
"""

UPDATE_UNVERIFIED_USER = """
MATCH (u:User {email: $email})
WHERE u.verified = false
SET u.password_hash = $password_hash, u.name = $name
RETURN u.email AS email, u.verified AS verified, u.name AS name
"""

GET_USER = """
MATCH (u:User {email: $email})
RETURN u.email AS email, u.verified AS verified, u.password_hash AS password_hash, u.name AS name
"""

SET_USER_VERIFIED = """
MATCH (u:User {email: $email})
SET u.verified = true, u.is_verified = true
WITH u
OPTIONAL MATCH (u)-[:HAS_OTP]->(o:Otp)
DETACH DELETE o
WITH u
RETURN u.email AS email, u.verified AS verified, u.name AS name
"""

REPLACE_OTP = """
MATCH (u:User {email: $email})
OPTIONAL MATCH (u)-[:HAS_OTP]->(old:Otp)
DETACH DELETE old
WITH u
CREATE (o:Otp {code: $code, expires_at: $expires_at, purpose: $purpose, created_at: $created_at})
CREATE (u)-[:HAS_OTP]->(o)
RETURN o.code AS code, o.expires_at AS expires_at
"""

GET_OTP = """
MATCH (u:User {email: $email})-[:HAS_OTP]->(o:Otp {purpose: $purpose})
RETURN o.code AS code, o.expires_at AS expires_at
"""

# ---------------------------------------------------------------------------
# Dashboard / historical
# ---------------------------------------------------------------------------

HOTEL_MONTHS = """
MATCH (h:Hotel {id: $hotel_id})-[:RECORDED]->(s:MonthlySnapshot)-[:IN_MONTH]->(m:Month)
WHERE s.source = 'upload'
  AND ($start_id IS NULL OR m.id >= $start_id)
  AND ($end_id IS NULL OR m.id <= $end_id)
RETURN m.id AS id,
       m.label AS label,
       m.year AS year,
       m.month AS month,
       m.date AS date,
       s.revenue AS revenue,
       s.expenses AS expenses,
       s.net_profit AS net_profit,
       s.occupancy AS occupancy,
       s.adr AS adr
ORDER BY m.year ASC, m.month ASC
"""

LATEST_MONTH = """
MATCH (h:Hotel {id: $hotel_id})-[:RECORDED]->(s:MonthlySnapshot)-[:IN_MONTH]->(m:Month)
WHERE s.source = 'upload'
RETURN m.id AS id, m.label AS label, m.year AS year, m.month AS month
ORDER BY m.year DESC, m.month DESC
LIMIT 1
"""

EXPENSE_BREAKDOWN = """
MATCH (h:Hotel {id: $hotel_id})-[:HAS_DEPARTMENT]->(d:Department)-[sp:SPENT_IN]->(m:Month {id: $month_id})
RETURN d.id AS id, d.name AS name, d.color AS color, sp.amount AS amount
ORDER BY sp.amount DESC
"""

FILTERED_EXPENSES = """
MATCH (h:Hotel {id: $hotel_id})-[:HAS_DEPARTMENT]->(d:Department)-[sp:SPENT_IN]->(m:Month)
WHERE ($start_id IS NULL OR m.id >= $start_id)
  AND ($end_id IS NULL OR m.id <= $end_id)
  AND ($category = 'All' OR d.name = $category)
RETURN m.id AS id,
       m.label AS label,
       m.date AS date,
       m.year AS year,
       m.month AS month,
       sum(sp.amount) AS category_expenses
ORDER BY m.year ASC, m.month ASC
"""

DEPARTMENT_NAMES = """
MATCH (h:Hotel {id: $hotel_id})-[:HAS_DEPARTMENT]->(d:Department)
RETURN d.name AS name
ORDER BY d.sort_order ASC
"""

# ---------------------------------------------------------------------------
# Graph-native queries (multi-hop / awkward in SQL)
# ---------------------------------------------------------------------------

# 3–4 hop: city event → month → hotel snapshot → occupancy-driven department spend.
EVENT_COST_CASCADE = """
MATCH (h:Hotel {id: $hotel_id})-[:LOCATED_IN]->(c:City)-[:HOSTED]->(e:CityEvent)-[:OCCURS_IN]->(m:Month)
MATCH (h)-[:RECORDED]->(s:MonthlySnapshot)-[:IN_MONTH]->(m)
MATCH (h)-[:HAS_DEPARTMENT]->(d:Department)-[sp:SPENT_IN]->(m)
MATCH (d)-[drv:COST_DRIVEN_BY]->(:DemandDriver {name: 'Occupancy'})
WHERE e.impact_score >= $min_impact
RETURN e.name AS event,
       e.type AS event_type,
       e.impact_score AS impact_score,
       m.label AS month,
       s.occupancy AS occupancy,
       s.revenue AS revenue,
       d.name AS department,
       sp.amount AS spend,
       drv.elasticity AS elasticity
ORDER BY e.impact_score DESC, sp.amount DESC
LIMIT 40
"""

# Analog months: same season + overlapping event types (set-overlap join).
ANALOG_MONTHS = """
MATCH (season:Season {name: $season})
MATCH (analog:Month)-[:IN_SEASON]->(season)
WHERE analog.year < $year OR (analog.year = $year AND analog.month < $month)
OPTIONAL MATCH (analog)<-[:OCCURS_IN]-(ae:CityEvent)
WITH analog, season, collect(DISTINCT ae.type) AS analog_events
MATCH (h:Hotel {id: $hotel_id})-[:RECORDED]->(s:MonthlySnapshot)-[:IN_MONTH]->(analog)
RETURN analog.id AS id,
       analog.label AS label,
       analog.year AS year,
       analog.month AS month,
       season.name AS season,
       s.revenue AS revenue,
       s.expenses AS expenses,
       s.occupancy AS occupancy,
       analog_events AS analog_events,
       $target_events AS target_events
ORDER BY analog.year DESC
"""

# Variable-length time-chain growth along NEXT relationships.
REVENUE_PATH_GROWTH = """
MATCH (start:Month {id: $start_id})
MATCH (end:Month {id: $end_id})
MATCH path = (start)-[:NEXT*1..24]->(end)
MATCH (h:Hotel {id: $hotel_id})-[:RECORDED]->(s0:MonthlySnapshot)-[:IN_MONTH]->(start)
MATCH (h)-[:RECORDED]->(s1:MonthlySnapshot)-[:IN_MONTH]->(end)
RETURN length(path) AS hops,
       s0.revenue AS start_revenue,
       s1.revenue AS end_revenue,
       s0.occupancy AS start_occupancy,
       s1.occupancy AS end_occupancy
"""

COMPETITOR_OCCUPANCY = """
MATCH (h:Hotel {id: $hotel_id})-[:COMPETES_WITH]->(c:Hotel)-[:RECORDED]->(s:MonthlySnapshot)-[:IN_MONTH]->(m:Month)
WHERE m.id = $month_id
MATCH (h)-[:RECORDED]->(ours:MonthlySnapshot)-[:IN_MONTH]->(m)
RETURN c.name AS competitor,
       s.occupancy AS competitor_occupancy,
       ours.occupancy AS our_occupancy,
       ours.occupancy - s.occupancy AS occupancy_gap
ORDER BY occupancy_gap DESC
"""

COST_DRIVER_ELASTICITIES = """
MATCH (h:Hotel {id: $hotel_id})-[:HAS_DEPARTMENT]->(d:Department)-[drv:COST_DRIVEN_BY]->(dd:DemandDriver)
RETURN d.name AS department, dd.name AS driver, drv.elasticity AS elasticity, d.color AS color
ORDER BY drv.elasticity DESC
"""

# ---------------------------------------------------------------------------
# Forecast persistence
# ---------------------------------------------------------------------------

CREATE_FORECAST_RUN = """
MATCH (h:Hotel {id: $hotel_id})
CREATE (r:ForecastRun {
  id: $run_id,
  created_at: $created_at,
  horizon_months: $horizon_months,
  model: $model
})
CREATE (h)-[:RAN_FORECAST]->(r)
RETURN r.id AS id
"""

UPSERT_FORECAST_MONTH = """
MATCH (h:Hotel {id: $hotel_id})-[:RAN_FORECAST]->(r:ForecastRun {id: $run_id})
MERGE (m:Month {id: $month_id})
  ON CREATE SET m.year = $year, m.month = $month, m.label = $label, m.date = $date
WITH h, r, m
MERGE (f:ForecastSnapshot {id: $snapshot_id})
SET f.revenue = $revenue,
    f.expenses = $expenses,
    f.net_profit = $net_profit,
    f.occupancy = $occupancy,
    f.adr = $adr
MERGE (r)-[:PROJECTS]->(f)
MERGE (f)-[:IN_MONTH]->(m)
RETURN f.id AS id
"""

GET_LATEST_FORECAST = """
MATCH (h:Hotel {id: $hotel_id})-[:RAN_FORECAST]->(r:ForecastRun)
WITH r
ORDER BY r.created_at DESC
LIMIT 1
MATCH (r)-[:PROJECTS]->(f:ForecastSnapshot)-[:IN_MONTH]->(m:Month)
RETURN r.id AS run_id,
       r.created_at AS created_at,
       r.horizon_months AS horizon_months,
       r.model AS model,
       m.id AS id,
       m.label AS label,
       m.year AS year,
       m.month AS month,
       m.date AS date,
       f.revenue AS revenue,
       f.expenses AS expenses,
       f.net_profit AS net_profit,
       f.occupancy AS occupancy,
       f.adr AS adr
ORDER BY m.year ASC, m.month ASC
"""

GET_HOTEL = """
MATCH (h:Hotel {id: $hotel_id})
OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
RETURN h.id AS id, h.name AS name, h.rooms AS rooms, h.star_rating AS star_rating, coalesce(c.name, '') AS city
"""

GET_ROOMS = """
MATCH (h:Hotel {id: $hotel_id})-[:OFFERS]->(r:RoomType)
WITH DISTINCT r
OPTIONAL MATCH (r)-[c:CONTRIBUTED_IN]->(:Month {id: $month_id})
WITH r,
     max(coalesce(c.occupancy_share, 0)) AS share,
     max(coalesce(c.revenue, 0)) AS revenue
RETURN r.id AS id,
       r.name AS name,
       r.base_rate AS base_rate,
       share,
       revenue
ORDER BY r.base_rate DESC
"""

UPDATE_USER_NAME = """
MATCH (u:User {email: $email})
SET u.name = $name
RETURN u.email AS email, u.name AS name
"""

LIST_USER_HOTELS = """
MATCH (u:User {email: $email})-[:OWNS]->(h:Hotel)
OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
RETURN DISTINCT h.id AS id, h.name AS name, h.rooms AS rooms, coalesce(c.name, '') AS city
ORDER BY h.name ASC
"""

LINK_USER_HOTEL = """
MATCH (u:User {email: $email})
MATCH (h:Hotel {id: $hotel_id})
MERGE (u)-[:OWNS]->(h)
RETURN h.id AS id
"""

CREATE_USER_HOTEL = """
MATCH (u:User {email: $email})
MERGE (c:City {id: $city_id})
SET c.name = $city_name
CREATE (h:Hotel {id: $hotel_id, name: $name, rooms: $rooms, star_rating: 0})
MERGE (h)-[:LOCATED_IN]->(c)
MERGE (u)-[:OWNS]->(h)
RETURN h.id AS id, h.name AS name, h.rooms AS rooms, c.name AS city
"""

GRAPH_DEPARTMENTS = """
MATCH (h:Hotel {id: $hotel_id})-[:HAS_DEPARTMENT]->(d:Department)
RETURN d.id AS id, d.name AS name, d.color AS color
ORDER BY d.sort_order ASC
"""

GRAPH_COMPETITORS = """
MATCH (h:Hotel {id: $hotel_id})-[:COMPETES_WITH]->(c:Hotel)
RETURN c.id AS id, c.name AS name, c.rooms AS rooms
"""

GRAPH_FORECAST = """
MATCH (h:Hotel {id: $hotel_id})-[:RAN_FORECAST]->(r:ForecastRun)
OPTIONAL MATCH (r)-[:PROJECTS]->(f:ForecastSnapshot)
RETURN r.id AS id, r.created_at AS created_at, count(f) AS months
ORDER BY r.created_at DESC
LIMIT 1
"""

