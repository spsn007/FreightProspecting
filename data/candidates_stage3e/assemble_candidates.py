"""
Stage 3E Candidate Assembler and Export
Imports all 5 verified tracks, runs them through CandidateValidator,
and exports the unified clean dataset to data/stage3e_verified_candidates.json.
"""

import json
from pathlib import Path
from data.candidates_stage3e.candidate_validator import CandidateValidator
from data.candidates_stage3e.track_a_us_wood import raw_track_a
from data.candidates_stage3e.track_b_ca_wood import raw_track_b
from data.candidates_stage3e.track_c_us_steel import raw_track_c
from data.candidates_stage3e.track_d_ca_steel import raw_track_d
from data.candidates_stage3e.track_e_precast_building import raw_track_e

def main():
    validator = CandidateValidator()
    
    tracks = [
        ("Track A (US Wood)", raw_track_a),
        ("Track B (Canada Wood)", raw_track_b),
        ("Track C (US Steel)", raw_track_c),
        ("Track D (Canada Steel)", raw_track_d),
        ("Track E (Precast Concrete)", raw_track_e),
    ]
    
    print("=" * 60)
    print("STAGE 3E CANDIDATE BATCH VALIDATION & ASSEMBLY")
    print("=" * 60)
    
    all_accepted = []
    
    for name, batch in tracks:
        accepted, rejected = validator.validate_batch(batch)
        print(f"{name:30} : {len(accepted):3} accepted, {len(rejected):3} rejected")
        if rejected:
            for r in rejected:
                print(f"  REJECTED: {r[0].get('brand')} -> {r[1]}")
        all_accepted.extend(accepted)
        
    stats = validator.get_stats()
    print("-" * 60)
    print(f"Total Accepted Candidates: {stats['total_accepted']}")
    print(f"Total Rejected Candidates: {stats['total_rejected']}")
    print(f"Unique New Operating Brands: {stats['unique_new_brands']}")
    print("-" * 60)
    
    output_path = Path("data/stage3e_verified_candidates.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_accepted, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully exported {len(all_accepted)} verified candidates to {output_path}")

if __name__ == "__main__":
    main()
