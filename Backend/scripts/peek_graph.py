from db import get_db

db = get_db()
db.verify()
print("connected_ok")

print("\n--- node counts ---")
for row in db.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC"):
    print(f"{row['label']}: {row['c']}")

print("\n--- users ---")
for u in db.run(
    "MATCH (u:User) RETURN u.email AS email, u.name AS name, u.verified AS verified ORDER BY coalesce(u.created_at,'') DESC LIMIT 10"
):
    print(u)

print("\n--- imported months ---")
for m in db.run(
    """
    MATCH (h:Hotel {id:'grand-metro'})-[:RECORDED]->(s:MonthlySnapshot)-[:IN_MONTH]->(m:Month)
    RETURN m.label AS label, s.source AS source, s.revenue AS revenue
    ORDER BY m.year DESC, m.month DESC
    LIMIT 10
    """
):
    print(m)

print("\n--- hotels ---")
for h in db.run("MATCH (h:Hotel) RETURN h.id AS id, h.name AS name, h.rooms AS rooms"):
    print(h)
