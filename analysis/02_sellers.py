# %% [markdown]
# # Scenario 2: Seller quality
#
# Business question: which sellers are reliably bad for the marketplace, and
# what do they cost it?
#
# "Reliably" is the hard part. A seller with 3 reviews averaging 1.7 might be
# fine and unlucky. We rank on a statistic that penalises small samples.
#
# Run from the project root:  python analysis/02_sellers.py
# Reads:  order_items_clean.csv, orders_clean.csv, reviews_dedup.csv, sellers_clean.csv
# Writes: outputs/exports/sellers_*.csv  and  outputs/figures/sellers_*.png

# %%
import polars as pl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# %%
pl.Config.set_tbl_rows(30)
pl.Config.set_tbl_cols(-1)
pl.Config.set_tbl_width_chars(200)
pl.Config.set_fmt_str_lengths(14)

# %%
MIN_REVIEWED_ORDERS = 20      # a seller needs this many reviewed orders to be ranked at all
WORST_N = 20                  # how many sellers to name on the slide

# %% [markdown]
# ## 1. Load

# %%
items = pl.read_csv("data/cleaned/order_items_clean.csv")
orders = pl.read_csv("data/cleaned/orders_clean.csv", try_parse_dates=True)
reviews = pl.read_csv("data/cleaned/reviews_dedup.csv")
sellers = pl.read_csv("data/cleaned/sellers_clean.csv",
                      schema_overrides={"seller_zip_code_prefix": pl.String})

# %%
items.shape, orders.shape, reviews.shape, sellers.shape

# %% [markdown]
# ## 2. One row per (seller, order)
# `order_items` has one row per item. An order with 3 items from the same seller
# would give that seller 3 copies of the same review. So first collapse to one
# row per seller per order, summing the money.

# %%
seller_orders = (
    items.group_by("seller_id", "order_id")
    .agg(
        pl.len().alias("n_items"),
        pl.col("price").sum().alias("revenue"),
        pl.col("freight_value").sum().alias("freight"),
    )
)
seller_orders.shape                       # fewer rows than items: multi-item orders collapsed

# %% [markdown]
# ## 3. Attach order status, delivery result, and the review
# Both joins are on `order_id` against tables that have one row per order, so
# the row count cannot change.

# %%
seller_orders = seller_orders.join(
    orders.select("order_id", "order_status", "valid_for_delay_calc", "delivery_status"),
    on="order_id", how="left",
)
seller_orders = seller_orders.join(reviews.select("order_id", "review_score"), on="order_id", how="left")
seller_orders.shape

# %%
seller_orders = seller_orders.with_columns(
    (pl.col("review_score") <= 2).alias("is_bad_review"),      # null stays null when there is no review
    (pl.col("order_status") == "canceled").alias("is_canceled"),
    (pl.col("delivery_status") == "late").alias("is_late"),
)
seller_orders.head(3)

# %% [markdown]
# ## 4. Aggregate to one row per seller
# `is_late` is only meaningful for delivered orders with valid timestamps, so
# the late rate is computed on that subset with a filter inside the aggregation.

# %%
per_seller = (
    seller_orders.group_by("seller_id")
    .agg(
        pl.len().alias("orders"),
        pl.col("review_score").is_not_null().sum().alias("reviewed_orders"),
        pl.col("review_score").mean().round(3).alias("mean_score"),
        pl.col("is_bad_review").sum().alias("bad_reviews"),
        pl.col("is_canceled").sum().alias("canceled_orders"),
        pl.col("is_late").filter(pl.col("valid_for_delay_calc") & (pl.col("order_status") == "delivered")).mean().round(4).alias("late_rate"),
        pl.col("revenue").sum().round(2).alias("revenue"),
    )
    .with_columns(
        (pl.col("bad_reviews") / pl.col("reviewed_orders")).round(4).alias("bad_share"),
        (pl.col("canceled_orders") / pl.col("orders")).round(4).alias("cancel_rate"),
    )
)
per_seller.shape

# %%
per_seller.sort("orders", descending=True).head(5)

# %% [markdown]
# ## 5. The trap this ranking avoids
# Sort by raw bad_share and the top of the list is sellers with 1 or 2 reviews.

# %%
per_seller.filter(pl.col("bad_share") == 1.0).sort("reviewed_orders").select("seller_id", "reviewed_orders", "bad_reviews", "bad_share").head(8)

# %%
per_seller.filter(pl.col("bad_share") == 1.0)["reviewed_orders"].value_counts().sort("reviewed_orders").head(6)

# %% [markdown]
# ## 6. Wilson lower bound
# For a proportion (here: share of reviewed orders that got 1 or 2 stars), the
# Wilson score interval gives a range the true share probably sits in.
# Its lower bound is what we rank on: "we are 95% sure at least this share of
# their orders got a bad review". Few reviews means a wide interval, so a
# 2-review seller with a 100% bad share gets a lower bound near 0.2, while a
# 60-review seller at 40% bad gets a lower bound near 0.29 and ranks above them.
#
# Formula, with p = bad_share, n = reviewed_orders, z = 1.96:
#   (p + z^2/2n - z * sqrt(p(1-p)/n + z^2/4n^2)) / (1 + z^2/n)

# %%
z = 1.96
p = pl.col("bad_share")
n = pl.col("reviewed_orders")
wilson_low = (p + z**2 / (2 * n) - z * ((p * (1 - p) / n) + z**2 / (4 * n**2)).sqrt()) / (1 + z**2 / n)

# %%
per_seller = per_seller.with_columns(wilson_low.round(4).alias("bad_share_lower_bound"))
per_seller.select("seller_id", "reviewed_orders", "bad_share", "bad_share_lower_bound").sort("bad_share_lower_bound", descending=True).head(5)

# %% [markdown]
# ## 7. Rank only sellers with enough reviews
# The Wilson bound already penalises small n, but a hard floor keeps the list
# defensible: every named seller has at least 20 reviewed orders.

# %%
ranked = (
    per_seller.filter(pl.col("reviewed_orders") >= MIN_REVIEWED_ORDERS)
    .sort("bad_share_lower_bound", descending=True)
    .with_row_index("rank", offset=1)
)
ranked.shape                              # how many sellers qualify

# %%
ranked = ranked.join(sellers.select("seller_id", "seller_state", "seller_city"), on="seller_id", how="left")
worst = ranked.head(WORST_N)
worst.select("rank", "seller_id", "seller_state", "reviewed_orders", "bad_share", "bad_share_lower_bound", "late_rate", "cancel_rate", "revenue")

# %% [markdown]
# ## 8. What do these sellers cost?
# Compare the worst 20 to everyone else who qualified.

# %%
rest = ranked.filter(pl.col("rank") > WORST_N)
comparison = pl.DataFrame({
    "group": [f"worst_{WORST_N}", "other_ranked_sellers"],
    "sellers": [worst.height, rest.height],
    "orders": [worst["orders"].sum(), rest["orders"].sum()],
    "revenue": [round(worst["revenue"].sum(), 2), round(rest["revenue"].sum(), 2)],
    "bad_share": [round(worst["bad_reviews"].sum() / worst["reviewed_orders"].sum(), 4),
                  round(rest["bad_reviews"].sum() / rest["reviewed_orders"].sum(), 4)],
    "late_rate": [round(float(worst["late_rate"].mean()), 4), round(float(rest["late_rate"].mean()), 4)],
    "cancel_rate": [round(worst["canceled_orders"].sum() / worst["orders"].sum(), 4),
                    round(rest["canceled_orders"].sum() / rest["orders"].sum(), 4)],
})
comparison

# %%
share_of_all_bad_reviews = worst["bad_reviews"].sum() / ranked["bad_reviews"].sum()
share_of_all_orders = worst["orders"].sum() / ranked["orders"].sum()
round(share_of_all_bad_reviews * 100, 1), round(share_of_all_orders * 100, 1)

# %% [markdown]
# ## 9. Are bad sellers bad because they are late?
# If bad_share tracks late_rate, the fix is logistics. If a seller has a high
# bad share and a normal late rate, the problem is the product or the service.

# %%
ranked.select(pl.corr("late_rate", "bad_share").alias("corr_late_vs_bad"))

# %%
worst.select("rank", "seller_id", "bad_share", "late_rate").with_columns(
    pl.when(pl.col("late_rate") > ranked["late_rate"].median() * 2).then(pl.lit("lateness"))
    .otherwise(pl.lit("product or service"))
    .alias("likely_cause")
)

# %% [markdown]
# ## 10. Export

# %%
ranked.write_csv("outputs/exports/sellers_ranked.csv")
worst.write_csv("outputs/exports/sellers_worst.csv")
comparison.write_csv("outputs/exports/sellers_comparison.csv")

# %% [markdown]
# ## 11. Figures

# %%
fig, ax = plt.subplots(figsize=(8, 6))
ax.barh([f"#{r} ({s[:8]})" for r, s in zip(worst["rank"].to_list(), worst["seller_id"].to_list())],
        (worst["bad_share_lower_bound"] * 100).to_list(), color="#C44E52")
ax.invert_yaxis()
ax.set_xlabel("Bad-review share, 95% lower bound (%)")
ax.set_title(f"{WORST_N} sellers with the most certain bad-review share (min {MIN_REVIEWED_ORDERS} reviewed orders)")
for i, (lb, n) in enumerate(zip(worst["bad_share_lower_bound"].to_list(), worst["reviewed_orders"].to_list())):
    ax.text(lb * 100 + 0.5, i, f"n={n}", va="center", fontsize=8)
plt.tight_layout()
plt.savefig("outputs/figures/sellers_worst_by_wilson.png", dpi=150)
plt.close()

# %%
fig, ax = plt.subplots(figsize=(7, 5.5))
ax.scatter((ranked["late_rate"] * 100).to_list(), (ranked["bad_share"] * 100).to_list(),
           s=12, alpha=0.4, color="#4C72B0", label="ranked sellers")
ax.scatter((worst["late_rate"] * 100).to_list(), (worst["bad_share"] * 100).to_list(),
           s=40, color="#C44E52", label=f"worst {WORST_N}")
ax.set_xlabel("Late delivery rate (%)")
ax.set_ylabel("Bad-review share (%)")
ax.set_title("Sellers: lateness vs bad reviews")
ax.legend()
plt.tight_layout()
plt.savefig("outputs/figures/sellers_late_vs_bad.png", dpi=150)
plt.close()

# %%
print("Scenario 2 done.")
print(f"  sellers with any order: {per_seller.height:,}   ranked (>= {MIN_REVIEWED_ORDERS} reviewed): {ranked.height:,}")
print(f"  worst {WORST_N}: {share_of_all_orders*100:.1f}% of ranked orders, {share_of_all_bad_reviews*100:.1f}% of ranked bad reviews")
print(f"  worst {WORST_N} bad share {comparison['bad_share'][0]*100:.1f}% vs others {comparison['bad_share'][1]*100:.1f}%")
