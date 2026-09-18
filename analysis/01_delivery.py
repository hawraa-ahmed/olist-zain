# %% [markdown]
# # Scenario 1: Late deliveries and customer satisfaction
#
# Business question: when an order arrives after the promised date, does the
# customer rate it worse, and by how much?
#
# Run from the project root:  python analysis/01_delivery.py
# Reads:  data/cleaned/orders_clean.csv, reviews_dedup.csv, order_items_agg.csv, customers_clean.csv
# Writes: outputs/exports/delivery_*.csv  and  outputs/figures/delivery_*.png

# %%
import polars as pl
from scipy import stats
import matplotlib
matplotlib.use("Agg")                     # draw to files, no window
import matplotlib.pyplot as plt

# %%
pl.Config.set_tbl_rows(30)
pl.Config.set_tbl_cols(-1)
pl.Config.set_tbl_width_chars(200)
pl.Config.set_fmt_str_lengths(14)

# %% [markdown]
# ## 1. Load
# `try_parse_dates=True` makes Polars read the timestamp columns as real
# Datetime instead of text, so we can subtract them later.

# %%
orders = pl.read_csv("data/cleaned/orders_clean.csv", try_parse_dates=True)
reviews = pl.read_csv("data/cleaned/reviews_dedup.csv", try_parse_dates=True)
items = pl.read_csv("data/cleaned/order_items_agg.csv")
customers = pl.read_csv("data/cleaned/customers_clean.csv",
                        schema_overrides={"customer_zip_code_prefix": pl.String})

# %%
orders.shape, reviews.shape, items.shape, customers.shape

# %%
orders.schema

# %% [markdown]
# ## 2. Keep only orders we can judge
# Three filters, all decided during cleaning:
# - status must be `delivered` (a shipped or canceled order has no delivery date to compare)
# - `valid_for_delay_calc` must be True (this drops the 1390 rows whose timestamps contradict each other)
# - the delivery date must exist (8 delivered orders have none)

# %%
orders["order_status"].value_counts().sort("count", descending=True)

# %%
delivered = orders.filter(
    (pl.col("order_status") == "delivered")
    & pl.col("valid_for_delay_calc")
    & pl.col("order_delivered_customer_date").is_not_null()
)
delivered.shape                          # 95,097 orders we can judge

# %% [markdown]
# ## 3. Attach the review and the order value
# `reviews_dedup` has exactly one row per order, so this join cannot multiply rows.
# `how="left"` keeps orders with no review; we count them, then drop them for the
# score analysis only.

# %%
delivered = delivered.join(reviews.select("order_id", "review_score"), on="order_id", how="left")
delivered = delivered.join(items.select("order_id", "item_price_total", "freight_value_total"), on="order_id", how="left")
delivered.shape                          # same row count as before the join

# %%
delivered.filter(pl.col("review_score").is_null()).height    # orders with no review at all

# %%
judged = delivered.filter(pl.col("review_score").is_not_null())
judged.shape

# %% [markdown]
# ## 4. The headline: late vs on time
# `delivery_status` and `days_late` were computed in cleaning:
# late means the order arrived on a later calendar date than the estimate.

# %%
summary = (
    judged.group_by("delivery_status")
    .agg(
        pl.len().alias("orders"),
        pl.col("review_score").mean().round(3).alias("mean_score"),
        (pl.col("review_score") <= 2).mean().round(4).alias("share_1_2_star"),
        (pl.col("review_score") == 1).mean().round(4).alias("share_1_star"),
        pl.col("item_price_total").sum().round(2).alias("revenue"),
    )
    .sort("delivery_status")
)
summary

# %%
late_rate = judged.filter(pl.col("delivery_status") == "late").height / judged.height
round(late_rate * 100, 2)               # % of judged orders that arrived late

# %% [markdown]
# ## 5. Is the gap real, and how big is it?
# Welch's t-test compares the two means without assuming equal spread.
# The confidence interval is the number to put on the slide: the gap in stars,
# with the range it could plausibly sit in.
# With ~95k orders almost any gap is "significant"; the interval is what tells
# you whether it is big enough to act on.

# %%
late_scores = judged.filter(pl.col("delivery_status") == "late")["review_score"].to_numpy()
ontime_scores = judged.filter(pl.col("delivery_status") == "on_time")["review_score"].to_numpy()
len(late_scores), len(ontime_scores)

# %%
test = stats.ttest_ind(ontime_scores, late_scores, equal_var=False)
ci = test.confidence_interval(confidence_level=0.95)
gap = float(ontime_scores.mean() - late_scores.mean())
round(gap, 3), (round(ci.low, 3), round(ci.high, 3)), test.pvalue

# %% [markdown]
# ## 6. Does it get worse the later it is?
# Bucket the delay to show a dose-response. If score keeps falling as delay
# grows, the relationship is not a fluke of one cutoff.

# %%
judged = judged.with_columns(
    pl.when(pl.col("days_late") <= 0).then(pl.lit("on time"))
    .when(pl.col("days_late") <= 3).then(pl.lit("1-3 days late"))
    .when(pl.col("days_late") <= 7).then(pl.lit("4-7 days late"))
    .when(pl.col("days_late") <= 14).then(pl.lit("8-14 days late"))
    .otherwise(pl.lit("15+ days late"))
    .alias("delay_bucket")
)

# %%
bucket_order = ["on time", "1-3 days late", "4-7 days late", "8-14 days late", "15+ days late"]
by_bucket = (
    judged.group_by("delay_bucket")
    .agg(
        pl.len().alias("orders"),
        pl.col("review_score").mean().round(3).alias("mean_score"),
        (pl.col("review_score") <= 2).mean().round(4).alias("share_1_2_star"),
    )
    .with_columns(pl.col("delay_bucket").replace_strict(bucket_order, list(range(5))).alias("order_key"))
    .sort("order_key")
    .drop("order_key")
)
by_bucket

# %% [markdown]
# ## 7. Where is it happening? Late rate by customer state
# Always carry the order count. A state with 40 orders and a state with
# 40,000 should not sit side by side as if they were equally certain.

# %%
judged = judged.join(customers.select("customer_id", "customer_state"), on="customer_id", how="left")

# %%
by_state = (
    judged.group_by("customer_state")
    .agg(
        pl.len().alias("orders"),
        (pl.col("delivery_status") == "late").mean().round(4).alias("late_rate"),
        pl.col("review_score").mean().round(3).alias("mean_score"),
        pl.col("days_late").filter(pl.col("delivery_status") == "late").mean().round(1).alias("avg_days_late_when_late"),
    )
    .sort("late_rate", descending=True)
)
by_state

# %% [markdown]
# ## 8. When is it happening? Late rate by purchase month
# If lateness spikes in specific months, the recommendation is about capacity
# planning, not about carriers.

# %%
by_month = (
    judged.with_columns(pl.col("order_purchase_timestamp").dt.strftime("%Y-%m").alias("month"))
    .group_by("month")
    .agg(
        pl.len().alias("orders"),
        (pl.col("delivery_status") == "late").mean().round(4).alias("late_rate"),
        pl.col("review_score").mean().round(3).alias("mean_score"),
    )
    .sort("month")
    .filter(pl.col("orders") >= 100)        # drop the first and last partial months
)
by_month

# %% [markdown]
# ## 9. Business impact
# Two numbers for the slide.
# - Revenue that arrived late: money tied to a bad experience.
# - "Excess" 1-2 star reviews: how many fewer bad reviews there would be if late
#   orders had the on-time bad-review rate. This is a what-if, not a measurement,
#   and the slide should say so.

# %%
late = judged.filter(pl.col("delivery_status") == "late")
late_revenue = late["item_price_total"].sum()
ontime_bad_rate = (judged.filter(pl.col("delivery_status") == "on_time")["review_score"] <= 2).mean()
late_bad_actual = (late["review_score"] <= 2).sum()
late_bad_expected = late.height * ontime_bad_rate
excess_bad_reviews = late_bad_actual - late_bad_expected
round(late_revenue, 2), late_bad_actual, round(late_bad_expected), round(excess_bad_reviews)

# %%
impact = pl.DataFrame({
    "metric": [
        "judged_orders", "late_orders", "late_rate",
        "mean_score_on_time", "mean_score_late", "score_gap", "score_gap_ci_low", "score_gap_ci_high",
        "share_1_2_star_on_time", "share_1_2_star_late",
        "late_revenue_brl", "excess_bad_reviews_from_lateness",
    ],
    "value": [
        float(judged.height), float(late.height), round(late_rate, 4),
        round(float(ontime_scores.mean()), 3), round(float(late_scores.mean()), 3),
        round(gap, 3), round(float(ci.low), 3), round(float(ci.high), 3),
        round(float(ontime_bad_rate), 4), round(float((late["review_score"] <= 2).mean()), 4),
        round(float(late_revenue), 2), float(round(float(excess_bad_reviews))),
    ],
})
impact                                   # one column of numbers, all Float64 so the table has one type

# %% [markdown]
# ## 10. Export for the dashboard
# Column names here are the contract with the dashboard. Do not rename them.

# %%
impact.write_csv("outputs/exports/delivery_summary.csv")
by_bucket.write_csv("outputs/exports/delivery_by_bucket.csv")
by_state.write_csv("outputs/exports/delivery_by_state.csv")
by_month.write_csv("outputs/exports/delivery_by_month.csv")

# %% [markdown]
# ## 11. Figures
# matplotlib takes plain lists, so each chart is: pull two columns out of a
# Polars table with `.to_list()`, hand them to a bar or line call, save.

# %%
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.bar(by_bucket["delay_bucket"].to_list(), by_bucket["mean_score"].to_list(), color="#4C72B0")
ax.set_ylim(1, 5)
ax.set_ylabel("Mean review score (1 to 5)")
ax.set_title("Review score falls as delivery delay grows")
for i, v in enumerate(by_bucket["mean_score"].to_list()):
    ax.text(i, v + 0.05, f"{v:.2f}", ha="center")
plt.tight_layout()
plt.savefig("outputs/figures/delivery_score_by_delay_bucket.png", dpi=150)
plt.close()

# %%
top_states = by_state.head(15)
fig, ax = plt.subplots(figsize=(8, 5))
ax.barh(top_states["customer_state"].to_list(), (top_states["late_rate"] * 100).to_list(), color="#DD8452")
ax.invert_yaxis()
ax.set_xlabel("Late delivery rate (%)")
ax.set_title("Late delivery rate, 15 worst states (label shows order count)")
for i, (rate, n) in enumerate(zip(top_states["late_rate"].to_list(), top_states["orders"].to_list())):
    ax.text(rate * 100 + 0.3, i, f"n={n:,}", va="center", fontsize=8)
plt.tight_layout()
plt.savefig("outputs/figures/delivery_late_rate_by_state.png", dpi=150)
plt.close()

# %%
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.plot(by_month["month"].to_list(), (by_month["late_rate"] * 100).to_list(), marker="o", color="#C44E52")
ax.set_ylabel("Late delivery rate (%)")
ax.set_title("Late delivery rate by purchase month")
ax.tick_params(axis="x", rotation=45)
plt.tight_layout()
plt.savefig("outputs/figures/delivery_late_rate_by_month.png", dpi=150)
plt.close()

# %%
print("Scenario 1 done.")
print(f"  judged orders: {judged.height:,}   late: {late.height:,} ({late_rate*100:.1f}%)")
print(f"  mean score on time {ontime_scores.mean():.2f} vs late {late_scores.mean():.2f}  gap {gap:.2f} stars  95% CI [{ci.low:.2f}, {ci.high:.2f}]")
print(f"  revenue delivered late: R$ {late_revenue:,.0f}   excess 1-2 star reviews: {excess_bad_reviews:,.0f}")
