"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "type": None, "idle_hours": 0})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # --- Extension 2: VRAM/MBU Right-sizing ---
    rightsize_recs = []
    rightsize_savings_monthly = 0.0
    for s in summary:
        mbu = s["mbu"]
        gtype = s["gpu_type"]
        cur_vram = num(cat[gtype]["hbm_gb"])
        cur_bw = num(cat[gtype]["peak_bw_tbs"])
        cur_cost = num(cat[gtype]["on_demand_hr"])
        achieved_bw = cur_bw * mbu

        if mbu < 0.30:
            best_alt = None
            best_alt_cost = cur_cost
            for alt_type, alt_det in cat.items():
                alt_cost = num(alt_det["on_demand_hr"])
                alt_vram = num(alt_det["hbm_gb"])
                alt_bw = num(alt_det["peak_bw_tbs"])

                if (alt_cost < cur_cost and 
                    alt_vram >= cur_vram and 
                    alt_bw >= achieved_bw):
                    if alt_cost < best_alt_cost:
                        best_alt = alt_type
                        best_alt_cost = alt_cost

            if best_alt:
                hourly_saving = cur_cost - best_alt_cost
                monthly_saving = hourly_saving * 24 * 30
                rightsize_savings_monthly += monthly_saving
                rightsize_recs.append({
                    "gpu_id": s["gpu_id"],
                    "current_gpu": gtype,
                    "current_cost": cur_cost,
                    "achieved_bw": round(achieved_bw, 3),
                    "recommended_gpu": best_alt,
                    "recommended_cost": best_alt_cost,
                    "hourly_savings": round(hourly_saving, 2),
                    "monthly_savings": round(monthly_saving, 2),
                    "reason": f"MBU={mbu:.1%} (achieved {achieved_bw:.3f} TB/s <= {cat[best_alt]['peak_bw_tbs']} TB/s peak of {best_alt})"
                })

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")
        
        print("\n== Extension 2: VRAM/MBU Right-sizing Recommendations ==")
        print(f"{'GPU ID':12}{'Current':9}{'Cost/h':>8}{'Ach.BW':>8}{'Recomm.':9}{'Cost/h':>8}{'Savings/mo':>12}")
        for r in rightsize_recs:
            print(f"{r['gpu_id']:12}{r['current_gpu']:9}${r['current_cost']:>7.2f}{r['achieved_bw']:>8.3f}{r['recommended_gpu']:9}${r['recommended_cost']:>7.2f}${r['monthly_savings']:>11.2f}")
        print(f"Total Right-sizing Monthly Savings: ${rightsize_savings_monthly:,.2f}")

    return {
        "summary": summary, 
        "lies": lies, 
        "idle_waste_daily": round(idle_waste, 2),
        "rightsize_mbu_recommendations": rightsize_recs,
        "rightsize_mbu_savings_monthly": round(rightsize_savings_monthly, 2)
    }


if __name__ == "__main__":
    run()
