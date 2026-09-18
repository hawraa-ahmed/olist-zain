# %% [markdown]
# # Scenario 3: Freight economics
#
# Business question: where does shipping cost eat a disproportionate share of
# what the customer pays for the product itself?
#
# One caveat that has to travel with every number here: the dataset has no
# product cost, so freight ratio is not profit margin. A category with a 40%
# freight ratio is a category where shipping adds 40% on top of the item
# price. Whether that loses money is unknown; whether it hurts conversion is
# the business argument.
#
# Run from the project root:  python analysis/03_freight.py
# Reads:  order_items_clean.csv, products_clean.csv, orders_clean.csv, customers_clean.csv, sellers_clean.csv
# Writes: outputs/exports/freight_*.csv  and  outputs/figures/freight_*.png

# %%
import polars as pl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# %%
pl.Config.set_tbl_rows(30)
pl.Config.set_tbl_cols(-1)
pl.Config.set_tbl_width_chars(200)
pl.Config.set_fmt_str_lengths(20)

# %%
MIN_ITEMS_PER_GROUP = 200     # a category or state needs this many items to be compared fairly

# %% [markdown]
# ## 1. Load

# %%
items = pl.read_csv("data/cleaned/order_items_clean.csv")
products = pl.read_csv("data/cleaned/products_clean.csv")
orders = pl.read_csv("data/cleaned/orders_clean.csv", try_parse_dates=True)
customers = pl.read_csv("data/cleaned/customers_clean.csv", schema_overrides={"customer_zip_code_prefix": pl.String})
sellers = pl.read_csv("data/cleaned/sellers_clean.csv", schema_overrides={"seller_zip_code_prefix": pl.String})

# %%
items.shape, products.shape

# %% [markdown]
# ## 2. Keep delivered orders only
# A canceled order was quoted freight but never shipped it. Delivered orders
# are the ones where the freight was actually paid and the goods actually moved.

# %%
items = items.join(orders.select("order_id", "order_status", "customer_id"), on="order_id", how="left")
items = items.filter(pl.col("order_status") == "delivered")
items.shape

# %% [markdown]
# ## 3. Attach category, customer state, seller state
# Three left joins, each against a table with one row per key, so no fan-out.

# %%
items = items.join(products.select("product_id", "product_category_name_english"), on="product_id", how="left")
items = items.join(customers.select("customer_id", "customer_state"), on="customer_id", how="left")
items = items.join(sellers.select("seller_id", "seller_state"), on="seller_id", how="left")
items.shape

# %%
items.select("product_category_name_english", "customer_state", "seller_state").null_count()

# %% [markdown]
# ## 4. The metric
# freight_ratio = freight_value / price, per item.
# When aggregating, use sum(freight) / sum(price), not the mean of the per-item
# ratios. The mean of ratios lets a R$5 item with R$15 freight (ratio 3.0) pull
# a whole category up; the ratio of sums weights every real (R$) equally.

# %%
items = items.with_columns(
    (pl.col("freight_value") / pl.col("price")).round(4).alias("freight_ratio"),
    (pl.col("freight_value") > pl.col("price")).alias("freight_exceeds_price"),
    (pl.col("seller_state") == pl.col("customer_state")).alias("same_state"),
)
items.select("price", "freight_value", "freight_ratio", "freight_exceeds_price").head(5)

# %%
overall = pl.DataFrame({
    "metric": ["items", "total_price", "total_freight", "freight_ratio_overall",
               "median_item_freight_ratio", "share_items_freight_exceeds_price"],
    "value": [
        float(items.height),
        round(float(items["price"].sum()), 2),
        round(float(items["freight_value"].sum()), 2),
        round(float(items["freight_value"].sum() / items["price"].sum()), 4),
        round(float(items["freight_ratio"].median()), 4),
        round(float(items["freight_exceeds_price"].mean()), 4),
    ],
})
overall

# %% [markdown]
# ## 5. By product category
# Only categories with at least 200 items are compared; the rest are listed
# but excluded from the "worst" ranking.

# %%
by_category = (
    items.group_by("product_category_name_english")
    .agg(
        pl.len().alias("items"),
        pl.col("price").sum().round(2).alias("total_price"),
        pl.col("freight_value").sum().round(2).alias("total_freight"),
        pl.col("price").mean().round(2).alias("avg_item_price"),
        pl.col("freight_exceeds_price").mean().round(4).alias("share_freight_exceeds_price"),
    )
    .with_columns((pl.col("total_freight") / pl.col("total_price")).round(4).alias("freight_ratio"))
    .with_columns((pl.col("items") >= MIN_ITEMS_PER_GROUP).alias("enough_items"))
    .sort("freight_ratio", descending=True)
)
by_category.filter(pl.col("enough_items")).head(15)

# %%
by_category.filter(pl.col("enough_items")).tail(5)       # the cheapest-to-ship categories, for contrast

# %% [markdown]
# ## 6. By price band
# This is what supports a minimum-order-value recommendation. If freight is
# 60% of a R$20 item and 8% of a R$200 item, the fix is not the carrier.

# %%
items = items.with_columns(
    pl.when(pl.col("price") < 25).then(pl.lit("a. under 25"))
    .when(pl.col("price") < 50).then(pl.lit("b. 25 to 50"))
    .when(pl.col("price") < 100).then(pl.lit("c. 50 to 100"))
    .when(pl.col("price") < 200).then(pl.lit("d. 100 to 200"))
    .otherwise(pl.lit("e. 200 and up"))
    .alias("price_band")
)

# %%
by_price_band = (
    items.group_by("price_band")
    .agg(
        pl.len().alias("items"),
        pl.col("price").sum().round(2).alias("total_price"),
        pl.col("freight_value").sum().round(2).alias("total_freight"),
        pl.col("freight_value").mean().round(2).alias("avg_freight"),
        pl.col("freight_exceeds_price").mean().round(4).alias("share_freight_exceeds_price"),
    )
    .with_columns((pl.col("total_freight") / pl.col("total_price")).round(4).alias("freight_ratio"))
    .sort("price_band")
)
by_price_band

# %% [markdown]
# ## 7. By customer state, and same-state vs cross-state
# Same-state shipping being much cheaper is the argument for regional
# fulfilment: stock popular items closer to where they are bought.

# %%
by_state = (
    items.group_by("customer_state")
    .agg(
        pl.len().alias("items"),
        pl.col("price").sum().round(2).alias("total_price"),
        pl.col("freight_value").sum().round(2).alias("total_freight"),
        pl.col("freight_value").mean().round(2).alias("avg_freight"),
        pl.col("same_state").mean().round(4).alias("share_same_state_seller"),
    )
    .with_columns((pl.col("total_freight") / pl.col("total_price")).round(4).alias("freight_ratio"))
    .with_columns((pl.col("items") >= MIN_ITEMS_PER_GROUP).alias("enough_items"))
    .sort("freight_ratio", descending=True)
)
by_state

# %%
same_vs_cross = (
    items.group_by("same_state")
    .agg(
        pl.len().alias("items"),
        pl.col("price").sum().round(2).alias("total_price"),
        pl.col("freight_value").sum().round(2).alias("total_freight"),
        pl.col("freight_value").mean().round(2).alias("avg_freight"),
    )
    .with_columns((pl.col("total_freight") / pl.col("total_price")).round(4).alias("freight_ratio"))
    .with_columns(pl.when(pl.col("same_state")).then(pl.lit("same state")).otherwise(pl.lit("cross state")).alias("route"))
    .select("route", "items", "total_price", "total_freight", "avg_freight", "freight_ratio")
    .sort("route")
)
same_vs_cross

# %%
share_cross_state = 1 - items["same_state"].mean()
round(share_cross_state * 100, 1)        # % of delivered items that crossed a state line

# %% [markdown]
# ## 8. Export

# %%
overall.write_csv("outputs/exports/freight_summary.csv")
by_category.write_csv("outputs/exports/freight_by_category.csv")
by_price_band.write_csv("outputs/exports/freight_by_price_band.csv")
by_state.write_csv("outputs/exports/freight_by_state.csv")
same_vs_cross.write_csv("outputs/exports/freight_same_vs_cross_state.csv")

# %% [markdown]
# ## 9. Figures

# %%
top_cat = by_category.filter(pl.col("enough_items")).head(15)
fig, ax = plt.subplots(figsize=(8, 6))
ax.barh(top_cat["product_category_name_english"].to_list(), (top_cat["freight_ratio"] * 100).to_list(), color="#8172B3")
ax.invert_yaxis()
ax.set_xlabel("Freight as % of item price")
ax.set_title("15 categories where shipping adds the most on top of price")
for i, (r, n) in enumerate(zip(top_cat["freight_ratio"].to_list(), top_cat["items"].to_list())):
    ax.text(r * 100 + 0.5, i, f"n={n:,}", va="center", fontsize=8)
plt.tight_layout()
plt.savefig("outputs/figures/freight_ratio_by_category.png", dpi=150)
plt.close()

# %%
fig, ax = plt.subplots(figsize=(8, 4.5))
labels = [b[3:] for b in by_price_band["price_band"].to_list()]      # strip the "a. " sort prefix
ax.bar(labels, (by_price_band["freight_ratio"] * 100).to_list(), color="#55A868")
ax.set_ylabel("Freight as % of item price")
ax.set_xlabel("Item price band (R$)")
ax.set_title("Cheap items carry the heaviest freight burden")
for i, v in enumerate(by_price_band["freight_ratio"].to_list()):
    ax.text(i, v * 100 + 1, f"{v*100:.0f}%", ha="center")
plt.tight_layout()
plt.savefig("outputs/figures/freight_ratio_by_price_band.png", dpi=150)
plt.close()

# %%
st = by_state.filter(pl.col("enough_items")).head(15)
fig, ax = plt.subplots(figsize=(8, 5.5))
ax.barh(st["customer_state"].to_list(), (st["freight_ratio"] * 100).to_list(), color="#DD8452")
ax.invert_yaxis()
ax.set_xlabel("Freight as % of item price")
ax.set_title("15 states with the heaviest freight burden (label: % of items from a same-state seller)")
for i, (r, s) in enumerate(zip(st["freight_ratio"].to_list(), st["share_same_state_seller"].to_list())):
    ax.text(r * 100 + 0.5, i, f"{s*100:.0f}% local", va="center", fontsize=8)
plt.tight_layout()
plt.savefig("outputs/figures/freight_ratio_by_state.png", dpi=150)
plt.close()

# %%
print("Scenario 3 done.")
print(f"  delivered items: {items.height:,}   overall freight ratio: {overall['value'][3]*100:.1f}%")
print(f"  items where freight > price: {overall['value'][5]*100:.1f}%")
print(f"  cross-state share: {share_cross_state*100:.1f}%   same-state ratio {same_vs_cross['freight_ratio'][1]*100:.1f}% vs cross-state {same_vs_cross['freight_ratio'][0]*100:.1f}%")
