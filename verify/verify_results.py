"""
Independent check of the analysis results.

Recomputes the headline numbers from the cleaned CSVs using only Python's
built-in csv module and plain loops. No Polars, no shared code with the
analysis scripts. If a number here matches the export, two different
implementations agree, which is the strongest evidence short of a third
person redoing it.

Run from the project root, after the three analysis scripts:
    python verify/verify_results.py
Exit code is non-zero on any failure.
"""

import csv
import math
import sys
from collections import defaultdict
from datetime import datetime

from scipy import stats

CLEAN = "data/cleaned/"
EXPORTS = "outputs/exports/"
failures = []


def check(name, got, want, tol=0.0):
    ok = abs(got - want) <= tol
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {got}, export says {want}")
    if not ok:
        failures.append(name)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def export_value(fname, key_col, key, val_col):
    for row in read_csv(EXPORTS + fname):
        if row[key_col] == key:
            return float(row[val_col])
    raise KeyError(f"{key} not in {fname}")


print("=" * 72)
print("SCENARIO 1: delivery")
print("=" * 72)

orders = read_csv(CLEAN + "orders_clean.csv")
reviews = {r["order_id"]: int(r["review_score"]) for r in read_csv(CLEAN + "reviews_dedup.csv")}
items_agg = {r["order_id"]: float(r["item_price_total"]) for r in read_csv(CLEAN + "order_items_agg.csv")}

# rebuild the judged set with the same three filters, but written by hand
judged = []
for o in orders:
    if o["order_status"] != "delivered":
        continue
    if o["valid_for_delay_calc"] != "True":     # pandas wrote the booleans as True/False
        continue
    if not o["order_delivered_customer_date"]:
        continue
    if o["order_id"] not in reviews:
        continue
    # recompute lateness from the raw timestamps rather than trusting days_late
    delivered = datetime.fromisoformat(o["order_delivered_customer_date"])
    estimated = datetime.fromisoformat(o["order_estimated_delivery_date"])
    is_late = delivered.date() > estimated.date()
    judged.append((is_late, reviews[o["order_id"]], items_agg.get(o["order_id"], 0.0)))

n_judged = len(judged)
late = [j for j in judged if j[0]]
ontime = [j for j in judged if not j[0]]
check("judged_orders", n_judged, export_value("delivery_summary.csv", "metric", "judged_orders", "value"))
check("late_orders", len(late), export_value("delivery_summary.csv", "metric", "late_orders", "value"))
check("late_rate", round(len(late) / n_judged, 4), export_value("delivery_summary.csv", "metric", "late_rate", "value"), tol=0.0001)

mean_late = sum(j[1] for j in late) / len(late)
mean_ontime = sum(j[1] for j in ontime) / len(ontime)
check("mean_score_late", round(mean_late, 3), export_value("delivery_summary.csv", "metric", "mean_score_late", "value"), tol=0.001)
check("mean_score_on_time", round(mean_ontime, 3), export_value("delivery_summary.csv", "metric", "mean_score_on_time", "value"), tol=0.001)
check("score_gap", round(mean_ontime - mean_late, 3), export_value("delivery_summary.csv", "metric", "score_gap", "value"), tol=0.001)

t = stats.ttest_ind([j[1] for j in ontime], [j[1] for j in late], equal_var=False)
ci = t.confidence_interval(0.95)
check("score_gap_ci_low", round(ci.low, 3), export_value("delivery_summary.csv", "metric", "score_gap_ci_low", "value"), tol=0.001)
check("score_gap_ci_high", round(ci.high, 3), export_value("delivery_summary.csv", "metric", "score_gap_ci_high", "value"), tol=0.001)

late_revenue = sum(j[2] for j in late)
check("late_revenue_brl", round(late_revenue, 2), export_value("delivery_summary.csv", "metric", "late_revenue_brl", "value"), tol=0.01)

bad_rate_ontime = sum(1 for j in ontime if j[1] <= 2) / len(ontime)
excess = sum(1 for j in late if j[1] <= 2) - len(late) * bad_rate_ontime
check("excess_bad_reviews", round(excess), export_value("delivery_summary.csv", "metric", "excess_bad_reviews_from_lateness", "value"), tol=1)

print()
print("=" * 72)
print("SCENARIO 2: sellers")
print("=" * 72)

order_info = {o["order_id"]: o for o in orders}
seller_order = defaultdict(set)          # maps each seller to the set of its order_ids
for r in read_csv(CLEAN + "order_items_clean.csv"):
    seller_order[r["seller_id"]].add(r["order_id"])

per_seller = {}
for seller, oids in seller_order.items():
    reviewed = [reviews[o] for o in oids if o in reviews]
    bad = sum(1 for s in reviewed if s <= 2)
    per_seller[seller] = (len(oids), len(reviewed), bad)

ranked_export = read_csv(EXPORTS + "sellers_ranked.csv")
n_ranked = sum(1 for s in per_seller.values() if s[1] >= 20)
check("ranked_seller_count", n_ranked, len(ranked_export))

# rank 1 seller: recompute its Wilson lower bound with scipy instead of the hand-written formula
top = ranked_export[0]
n, bad = per_seller[top["seller_id"]][1], per_seller[top["seller_id"]][2]
scipy_low = stats.binomtest(bad, n).proportion_ci(confidence_level=0.95, method="wilson").low
check("rank1_reviewed_orders", n, float(top["reviewed_orders"]))
check("rank1_bad_reviews", bad, float(top["bad_reviews"]))
check("rank1_wilson_lower_bound_vs_scipy", round(scipy_low, 4), float(top["bad_share_lower_bound"]), tol=0.0005)

# is the export actually sorted by that bound?
bounds = [float(r["bad_share_lower_bound"]) for r in ranked_export]
check("ranked_export_sorted_descending", int(bounds == sorted(bounds, reverse=True)), 1)

# worst-20 bad share
worst_ids = [r["seller_id"] for r in ranked_export[:20]]
w_reviewed = sum(per_seller[s][1] for s in worst_ids)
w_bad = sum(per_seller[s][2] for s in worst_ids)
check("worst20_bad_share", round(w_bad / w_reviewed, 4), export_value("sellers_comparison.csv", "group", "worst_20", "bad_share"), tol=0.0001)

print()
print("=" * 72)
print("SCENARIO 3: freight")
print("=" * 72)

status = {o["order_id"]: o["order_status"] for o in orders}
total_price = total_freight = 0.0
n_items = n_exceeds = 0
band_price = defaultdict(float)
band_freight = defaultdict(float)
for r in read_csv(CLEAN + "order_items_clean.csv"):
    if status.get(r["order_id"]) != "delivered":
        continue
    p, f = float(r["price"]), float(r["freight_value"])
    n_items += 1
    total_price += p
    total_freight += f
    if f > p:
        n_exceeds += 1
    band = "a. under 25" if p < 25 else "b. 25 to 50" if p < 50 else "c. 50 to 100" if p < 100 else "d. 100 to 200" if p < 200 else "e. 200 and up"
    band_price[band] += p
    band_freight[band] += f

check("delivered_items", n_items, export_value("freight_summary.csv", "metric", "items", "value"))
check("freight_ratio_overall", round(total_freight / total_price, 4), export_value("freight_summary.csv", "metric", "freight_ratio_overall", "value"), tol=0.0001)
check("share_freight_exceeds_price", round(n_exceeds / n_items, 4), export_value("freight_summary.csv", "metric", "share_items_freight_exceeds_price", "value"), tol=0.0001)
check("under_25_freight_ratio", round(band_freight["a. under 25"] / band_price["a. under 25"], 4),
      export_value("freight_by_price_band.csv", "price_band", "a. under 25", "freight_ratio"), tol=0.0001)
check("200_and_up_freight_ratio", round(band_freight["e. 200 and up"] / band_price["e. 200 and up"], 4),
      export_value("freight_by_price_band.csv", "price_band", "e. 200 and up", "freight_ratio"), tol=0.0001)

print()
print("=" * 72)
if failures:
    print(f"{len(failures)} CHECK(S) FAILED: {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED: the plain-Python recomputation matches every exported headline number.")
