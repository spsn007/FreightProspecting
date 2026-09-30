import json
with open('reports/tier_a_phase_b_wave_B_change_plan.json', 'r', encoding='utf-8') as f:
    plan = json.load(f)

a_promos = [p for p in plan if p['expected_engine_effect'] == 'TIER_A_PROMOTION']
print(f'Tier A promotions in plan ({len(a_promos)}):')
for p in a_promos:
    print(f"  Pos {p['campaign_position']:02d}: CID {p['company_id']:3d} ({p['operating_brand']}) Claims: {len(p['proposed_claims'])}")
