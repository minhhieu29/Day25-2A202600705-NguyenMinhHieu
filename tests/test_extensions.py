import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from finops import pricing, sustainability
from missions import m1_efficiency_audit, m3_purchasing


def test_advanced_recommend_tier():
    # Standard check (should still work as expected)
    assert pricing.recommend_tier(4, False) == "on_demand"
    assert pricing.recommend_tier(24, False) == "reserved"
    assert pricing.recommend_tier(2, True) == "spot"

    # Short duration checks (Extension 1)
    # Even if duty cycle is high (24h/day), if the job only runs for 5 days, recommend on-demand rather than reserved commitment
    assert pricing.recommend_tier(24, False, job_days=5) == "on_demand"
    assert pricing.recommend_tier(24, False, job_days=30) == "reserved"
    # Short duration interruptible job should recommend spot
    assert pricing.recommend_tier(24, True, job_days=5) == "spot"


def test_vram_mbu_rightsizing():
    res = m1_efficiency_audit.run(verbose=False)
    assert "rightsize_mbu_recommendations" in res
    assert "rightsize_mbu_savings_monthly" in res
    
    recs = res["rightsize_mbu_recommendations"]
    assert len(recs) > 0
    # gpu-h100-4 is H100 with low MBU (20.7%), should suggest A100
    h100_4_rec = [r for r in recs if r["gpu_id"] == "gpu-h100-4"]
    assert len(h100_4_rec) == 1
    assert h100_4_rec[0]["recommended_gpu"] == "A100"
    assert h100_4_rec[0]["monthly_savings"] == round(0.71 * 24 * 30, 2)


def test_carbon_aware_scheduling():
    res = m3_purchasing.run(verbose=False)
    assert "carbon_scheduling" in res
    data = res["carbon_scheduling"]
    
    # 1789 kWh total workload energy
    assert data["total_energy_kwh"] == 1789.0
    assert data["carbon_saved_kg"] > 0
    assert data["carbon_saved_pct"] == 92.1  # 92.1% saved going to europe-north1
