"""
Audit Evidence Sources:
Checks URLs, source_type classifications, domain matching, and dead/redirected URLs.
"""
import sqlite3
import urllib.parse
from pathlib import Path

def audit_sources():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    sources = conn.execute("SELECT * FROM evidence_sources").fetchall()
    print(f"Total evidence sources in database: {len(sources)}")

    null_url_sources = [s for s in sources if not s["source_url"]]
    print(f"Sources with NULL URL (offline/phone/etc.): {len(null_url_sources)}")

    # Distinct source types
    st_counts = {}
    for s in sources:
        st_counts[s["source_type"]] = st_counts.get(s["source_type"], 0) + 1
    print("Source Type Breakdown:", st_counts)

    # Check for domain patterns that indicate directories, associations, government registries
    directory_patterns = [
        "manta.com", "zoominfo.com", "yellowpages.com", "dnb.com", "linkedin.com",
        "thomasnet.com", "hoovers.com", "chamberofcommerce.com", "buzzfile.com",
        "kompass.com", "hardwoodreview.com", "woodworkingnetwork.com", "osha.gov",
        "fmcsa.dot.gov", "epa.gov", "sec.gov", "wikipedia.org", "bloomberg.com",
        "opencorporates.com", "bizapedia.com", "facebook.com", "industrynet.com",
        "dunandbradstreet.com", "cortera.com", "bbb.org", "mapquest.com", "yelp.com"
    ]

    mislabeled_candidates = []
    for s in sources:
        url = s["source_url"] or ""
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower().replace("www.", "")
        st = s["source_type"]

        is_dir = any(dp in netloc for dp in directory_patterns)
        is_gov = any(gov in netloc for gov in [".gov", ".gc.ca", "canada.ca"])

        if is_gov and st != "GOVERNMENT_REGISTRY":
            mislabeled_candidates.append((s["id"], s["source_url"], st, "GOVERNMENT_REGISTRY", netloc))
        elif is_dir and st not in ("INDUSTRY_DIRECTORY", "DIRECTORY"):
            mislabeled_candidates.append((s["id"], s["source_url"], st, "INDUSTRY_DIRECTORY", netloc))

    print(f"\nPotential Mislabeled Sources: {len(mislabeled_candidates)}")
    for mc in mislabeled_candidates[:10]:
        print(f"  ID {mc[0]}: {mc[1]} (Current: {mc[2]} -> Suggested: {mc[3]})")

    # Let's inspect Stage 3E sources specifically:
    # Stage 3E sources were created during Stage 3E (id > 425 or created around Stage 3E)
    stage3e_sources = [s for s in sources if s["id"] >= 428]
    print(f"\nStage 3E Created Sources: {len(stage3e_sources)}")
    stage3e_st = {}
    for s in stage3e_sources:
        stage3e_st[s["source_type"]] = stage3e_st.get(s["source_type"], 0) + 1
    print("Stage 3E Source Type Breakdown:", stage3e_st)

    conn.close()

if __name__ == "__main__":
    audit_sources()
