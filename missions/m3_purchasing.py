"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing, sustainability

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        # Call with advanced logic parameters (Extension 1)
        tier = pricing.recommend_tier(hpd, interruptible, gpu_type=gtype, job_days=num(j.get("days", 30)))
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(gpu_hours, num(c["spot_hr"]), od)
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            opt_cost = gpu_hours * num(c["reserved_3yr_hr"])
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    # --- Extension 5: Carbon-aware Scheduling ---
    total_energy_wh = 0.0
    for j in jobs:
        if bool(int(num(j["interruptible"]))):
            gtype = j["gpu_type"]
            watts = num(cat[gtype]["watts"])
            ngpus = int(num(j["num_gpus"]))
            hpd = num(j["hours_per_day"])
            days = num(j["days"])
            # energy for the entire job duration
            total_energy_wh += ngpus * hpd * days * watts

    region_comparison = []
    for region in sustainability.REGION_CARBON.keys():
        carbon = sustainability.carbon_g(total_energy_wh, region)
        cost = sustainability.energy_cost_usd(total_energy_wh, region)
        region_comparison.append({
            "region": region,
            "carbon_g": round(carbon, 1),
            "cost_usd": round(cost, 2),
            "carbon_intensity": sustainability.REGION_CARBON[region],
            "price_kwh": sustainability.REGION_PRICE_KWH[region]
        })

    # us-east-1 is the baseline region
    baseline_region = "us-east-1"
    cleanest_region = "europe-north1"
    cheapest_region = "us-east-wa"

    base_carbon = sustainability.carbon_g(total_energy_wh, baseline_region)
    clean_carbon = sustainability.carbon_g(total_energy_wh, cleanest_region)
    carbon_saved = base_carbon - clean_carbon
    carbon_saved_pct = (carbon_saved / base_carbon * 100) if base_carbon > 0 else 0.0

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")

        print("\n== Extension 5: Carbon-aware Scheduling Analysis (Interruptible Workloads) ==")
        print(f"Total workload energy consumption: {total_energy_wh/1000.0:,.2f} kWh")
        print(f"{'Region':18}{'Carbon (gCO2e)':>16}{'Energy Cost ($)':>16}{'Intensity (g/kWh)':>20}{'Price ($/kWh)':>15}")
        for reg in region_comparison:
            print(f"{reg['region']:18}{reg['carbon_g']:>16,.1f}{reg['cost_usd']:>16,.2f}{reg['carbon_intensity']:>20}{reg['price_kwh']:>15}")
        print(f"\nCarbon savings by moving to cleanest ({cleanest_region}): {carbon_saved/1000.0:,.2f} kgCO2e saved ({carbon_saved_pct:.1f}% reduction)")

    return {
        "recommendations": recs, 
        "on_demand_monthly": round(on_demand_monthly),
        "optimized_monthly": round(optimized_monthly), 
        "savings_pct": round(savings_pct, 1),
        "carbon_scheduling": {
            "total_energy_kwh": round(total_energy_wh / 1000.0, 2),
            "region_comparison": region_comparison,
            "carbon_saved_kg": round(carbon_saved / 1000.0, 2),
            "carbon_saved_pct": round(carbon_saved_pct, 1)
        }
    }


if __name__ == "__main__":
    run()
