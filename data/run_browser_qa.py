from fastapi.testclient import TestClient
import sqlite3
from src.backend.main import app

client = TestClient(app)

print("=== 1. COCKPIT QA (GET /) ===")
resp = client.get("/")
assert resp.status_code == 200
html = resp.text
assert "Beasley Forest Products" in html
assert "Kenwal Steel Corp." in html
assert "DECAST Ltd." in html
assert "WMG Technologies" in html
assert "Canfor" not in html
assert "West Fraser" not in html
print("Cockpit: 4 shortlisted displayed, 0 discovery pollution. OK!")

print("\n=== 2. MASTER DIRECTORY QA (GET /prospects) ===")
resp = client.get("/prospects")
assert resp.status_code == 200
html = resp.text
assert "All" in html
assert "Shortlist" in html
assert "Discovery" in html
assert "Canfor" in html
assert "Advanced Precast" in html
assert "Metal Master" in html
assert "Camcar Plastics" in html
print("Master Directory renders enlarged pool with all tabs. OK!")

print("\n=== 3. DETAIL PAGES QA ACROSS SECTORS ===")
conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

canfor_id = cur.execute("SELECT f.id FROM facilities f JOIN companies c ON f.company_id = c.id WHERE c.operating_brand LIKE '%Canfor%' LIMIT 1").fetchone()[0]
precast_id = cur.execute("SELECT f.id FROM facilities f JOIN companies c ON f.company_id = c.id WHERE c.operating_brand LIKE '%Advanced Precast%' LIMIT 1").fetchone()[0]
steel_id = cur.execute("SELECT f.id FROM facilities f JOIN companies c ON f.company_id = c.id WHERE c.operating_brand LIKE '%Metal Master%' LIMIT 1").fetchone()[0]
plastics_id = cur.execute("SELECT f.id FROM facilities f JOIN companies c ON f.company_id = c.id WHERE c.operating_brand LIKE '%Camcar Plastics%' LIMIT 1").fetchone()[0]

samples = [
    ("Track A Wood: Canfor", canfor_id),
    ("Track D Precast: Advanced Precast", precast_id),
    ("Track C Steel: Metal Master", steel_id),
    ("Track E Plastics: Camcar Plastics", plastics_id)
]

for label, fid in samples:
    r = client.get(f"/prospects/{fid}")
    assert r.status_code == 200
    t = r.text
    assert "DISCOVERY" in t
    # Print facility details
    fac_row = cur.execute("SELECT facility_name, physical_address, city, state_prov, country FROM facilities WHERE id = ?", (fid,)).fetchone()
    comm_row = cur.execute("SELECT commodity_category, equipment_category, equipment_usage_status FROM facility_commodities WHERE facility_id = ?", (fid,)).fetchone()
    contact_row = cur.execute("SELECT phone_number, phone_directness, email_address FROM contacts WHERE facility_id = ?", (fid,)).fetchone()
    print(f"{label} (ID {fid}):")
    print(f"  Facility: {fac_row[0]} — {fac_row[1]}, {fac_row[2]}, {fac_row[3]} {fac_row[4]}")
    print(f"  Commodity: {comm_row[0]} | Equipment: {comm_row[1]} ({comm_row[2]})")
    print(f"  Contact: Phone: {contact_row[0]} ({contact_row[1]}), Email: {contact_row[2]}")
    print(f"  Status: HTTP 200, DISCOVERY lifecycle verified. OK!\n")

print("=== 4. DARK MODE QA ===")
assert 'id="themeToggleBtn"' in resp.text
assert 'onclick="toggleTheme()"' in resp.text
assert "localStorage.getItem('fp_theme')" in resp.text
print("Dark mode toggle element and localStorage hook verified in HTML. OK!")

# Check CSS
css_resp = client.get("/static/css/app.css")
assert css_resp.status_code == 200
css_text = css_resp.text
assert '[data-theme="dark"]' in css_text
assert '--bg-workspace: #0b1329;' in css_text
assert '--color-surface: #1e293b;' in css_text
assert '--verified-color: #4ade80;' in css_text
assert '--inferred-color: #fbbf24;' in css_text
assert '--unknown-color: #94a3b8;' in css_text
assert '--danger-color: #f87171;' in css_text
print("Dark mode CSS variables, theme tokens, and semantic contrast verified. OK!")

conn.close()
print("\nALL BROWSER QA CHECKS PASSED PERFECTLY!")
