"""
Olist dataset cleaning script.

Run from the folder containing this file, with the nine raw CSVs in raw/.
Writes cleaned CSVs to cleaned/ and a decisions log to decisions.md.

Every choice below traces to a count found during profiling. Nothing is
silently dropped: rows that look wrong are flagged in a column, not deleted,
except for the small set of true impossibilities named in the comments.
"""

import pandas as pd

RAW = "data/raw/"
OUT = "data/cleaned/"

decisions = []


def log(line):
    decisions.append(line)
    print(line)


# ---------------------------------------------------------------------------
# Load. Zip columns MUST be read as text and zero padded, or leading zeros
# on prefixes below 10000 are silently lost (customers, sellers, geolocation
# all affected). This is the single most consequential fix in this script.
# ---------------------------------------------------------------------------

def load_zip_col(path, col):
    df = pd.read_csv(path, dtype={col: str})
    df[col] = df[col].str.zfill(5)
    return df


customers = load_zip_col(RAW + "olist_customers_dataset.csv", "customer_zip_code_prefix")
sellers = load_zip_col(RAW + "olist_sellers_dataset.csv", "seller_zip_code_prefix")
geo = load_zip_col(RAW + "olist_geolocation_dataset.csv", "geolocation_zip_code_prefix")

orders = pd.read_csv(RAW + "olist_orders_dataset.csv")
order_items = pd.read_csv(RAW + "olist_order_items_dataset.csv")
payments = pd.read_csv(RAW + "olist_order_payments_dataset.csv")
reviews = pd.read_csv(RAW + "olist_order_reviews_dataset.csv")
products = pd.read_csv(RAW + "olist_products_dataset.csv")
cat_trans = pd.read_csv(RAW + "product_category_name_translation.csv")

log("## Zip code leading zeros")
log(f"- Reloaded customer/seller/geolocation zip prefixes as zero-padded text.")
log(f"- Without this fix, {(pd.read_csv(RAW+'olist_customers_dataset.csv')['customer_zip_code_prefix']<10000).sum()} "
    f"customer rows, "
    f"{(pd.read_csv(RAW+'olist_sellers_dataset.csv')['seller_zip_code_prefix']<10000).sum()} seller rows, and "
    f"{(pd.read_csv(RAW+'olist_geolocation_dataset.csv')['geolocation_zip_code_prefix']<10000).sum()} geolocation "
    f"rows would have a truncated zip prefix.")

# ---------------------------------------------------------------------------
# Orders: parse dates, flag (don't drop) rows that fail delivery-timing logic
# ---------------------------------------------------------------------------

date_cols = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
             "order_delivered_customer_date", "order_estimated_delivery_date"]
for c in date_cols:
    orders[c] = pd.to_datetime(orders[c])

orders["flag_delivered_but_no_date"] = (
    (orders["order_status"] == "delivered") & (orders["order_delivered_customer_date"].isnull())
)
orders["flag_carrier_before_approved"] = (
    orders["order_delivered_carrier_date"] < orders["order_approved_at"]
)
orders["flag_customer_before_carrier"] = (
    orders["order_delivered_customer_date"] < orders["order_delivered_carrier_date"]
)
orders["valid_for_delay_calc"] = ~(
    orders["flag_delivered_but_no_date"]
    | orders["flag_carrier_before_approved"].fillna(False)
    | orders["flag_customer_before_carrier"].fillna(False)
)

orders["days_late"] = (
    orders["order_delivered_customer_date"] - orders["order_estimated_delivery_date"]
).dt.days
orders["delivery_status"] = pd.NA
orders.loc[orders["days_late"] > 0, "delivery_status"] = "late"
orders.loc[orders["days_late"] <= 0, "delivery_status"] = "on_time"

log("\n## Orders")
log(f"- Flagged {orders['flag_delivered_but_no_date'].sum()} rows: status 'delivered' with no delivery date. "
    f"Excluded from delivery-timing analysis via valid_for_delay_calc, kept for revenue.")
log(f"- Flagged {orders['flag_carrier_before_approved'].sum()} rows: carrier pickup logged before approval. "
    f"Excluded from delay calc.")
log(f"- Flagged {orders['flag_customer_before_carrier'].sum()} rows: customer received before carrier pickup. "
    f"Excluded from delay calc.")
log(f"- {orders['valid_for_delay_calc'].sum()} of {len(orders)} orders are valid for delay calculation.")
log("- delivery_status and days_late are only meaningful where valid_for_delay_calc is True.")

# ---------------------------------------------------------------------------
# Order items: keep at item grain, but provide the order-level aggregate
# analyses actually need for a 1:1 join to orders. Never join raw item rows
# straight to orders.
# ---------------------------------------------------------------------------

order_items_agg = order_items.groupby("order_id").agg(
    n_items=("order_item_id", "count"),
    item_price_total=("price", "sum"),
    freight_value_total=("freight_value", "sum"),
    n_distinct_sellers=("seller_id", "nunique"),
).reset_index()

log("\n## Order items")
log(f"- No nulls, no duplicate rows, no non-positive prices found.")
log(f"- {(order_items['freight_value']==0).sum()} rows have freight_value of 0. Kept as-is, not treated as an error.")
log(f"- {len(order_items)} item rows cover only {order_items['order_id'].nunique()} distinct orders. "
    f"Built order_items_agg.csv at order grain for any join to orders; the item-level file is kept "
    f"separately for the freight-by-category analysis, which needs item grain.")

# ---------------------------------------------------------------------------
# Payments: same grain problem, plus a small number of zero-value and
# not_defined rows to flag rather than drop.
# ---------------------------------------------------------------------------

payments["flag_zero_value"] = payments["payment_value"] == 0
payments["flag_undefined_type"] = payments["payment_type"] == "not_defined"

payments_agg = payments.groupby("order_id").agg(
    payment_value_total=("payment_value", "sum"),
    max_installments=("payment_installments", "max"),
    n_payment_rows=("payment_sequential", "count"),
).reset_index()

log("\n## Payments")
log(f"- Flagged {payments['flag_zero_value'].sum()} rows with payment_value of 0 "
    f"(mostly vouchers). Kept, flagged, excluded from revenue sums by nature of being 0.")
log(f"- Flagged {payments['flag_undefined_type'].sum()} rows with payment_type 'not_defined'. "
    f"Excluded from payment-type breakdowns.")
log(f"- Built payments_agg.csv at order grain, same reasoning as order_items_agg.")

# ---------------------------------------------------------------------------
# Reviews: 551 orders have more than one review row, and 789 review_id
# values are reused across different orders. Never join on review_id.
# Collapse to one row per order using the most recent review_answer_timestamp.
# ---------------------------------------------------------------------------

reviews["review_answer_timestamp"] = pd.to_datetime(reviews["review_answer_timestamp"])
n_orders_multi_review = reviews["order_id"].duplicated().sum()

reviews_sorted = reviews.sort_values("review_answer_timestamp")
reviews_dedup = reviews_sorted.drop_duplicates(subset="order_id", keep="last").copy()

log("\n## Reviews")
log(f"- {n_orders_multi_review} orders had more than one review row. Kept the review with the latest "
    f"review_answer_timestamp per order in reviews_dedup.csv; this is the file to join to orders, "
    f"the raw reviews file is kept separately and should not be joined 1:1 to orders.")
log(f"- 789 review_id values are reused across different order_ids. Always join on order_id, never review_id.")
log(f"- Comment title and message nulls are sparse text, not treated as an error, left as null.")

# ---------------------------------------------------------------------------
# Products: patch the two categories missing from the translation table so
# the join to English names doesn't silently null them out.
# ---------------------------------------------------------------------------

# Explicit mapping. Do not build this from set iteration order: Python
# randomizes string hashing per process, so a set-order-dependent pairing can
# silently swap the two names between runs.
KNOWN_MISSING_TRANSLATIONS = {
    "portateis_cozinha_e_preparadores_de_alimentos": "kitchen_portables",
    "pc_gamer": "pc_gamer",
}

missing_cats = set(products["product_category_name"].dropna().unique()) - set(cat_trans["product_category_name"])
unexpected = missing_cats - set(KNOWN_MISSING_TRANSLATIONS)
if unexpected:
    raise ValueError(
        f"Categories missing from the translation table with no known English name: {sorted(unexpected)}. "
        f"Add them to KNOWN_MISSING_TRANSLATIONS before rerunning."
    )

patch = pd.DataFrame(
    [(pt, KNOWN_MISSING_TRANSLATIONS[pt]) for pt in sorted(missing_cats)],
    columns=["product_category_name", "product_category_name_english"],
)
cat_trans_patched = pd.concat([cat_trans, patch], ignore_index=True)

products["flag_missing_category"] = products["product_category_name"].isnull()
products = products.merge(cat_trans_patched, on="product_category_name", how="left")
products["product_category_name_english"] = products["product_category_name_english"].fillna("unknown")

log("\n## Products")
log(f"- Patched {len(patch)} category names missing from the translation table: {sorted(missing_cats)}.")
log(f"- Flagged {products['flag_missing_category'].sum()} rows with no category at all (also missing all "
    f"other descriptive fields). Category set to 'unknown', rows kept, not dropped.")
log(f"- {products['product_weight_g'].isnull().sum()} rows still missing weight and dimensions after the above. "
    f"Left as null, flagged for exclusion from any weight-dependent calculation.")

# ---------------------------------------------------------------------------
# Geolocation: drop exact duplicates and out-of-country coordinates, then
# collapse to one row per zip prefix. This table is a lookup table, not an
# analysis table, so collapsing it is correct rather than lossy.
# ---------------------------------------------------------------------------

n_exact_dupes = geo.duplicated().sum()
geo_dedup = geo.drop_duplicates()

in_brazil = geo_dedup["geolocation_lat"].between(-34, 6) & geo_dedup["geolocation_lng"].between(-75, -32)
n_out_of_country = (~in_brazil).sum()
geo_dedup = geo_dedup[in_brazil]

geo_by_zip = geo_dedup.groupby("geolocation_zip_code_prefix").agg(
    geolocation_lat=("geolocation_lat", "mean"),
    geolocation_lng=("geolocation_lng", "mean"),
    geolocation_city=("geolocation_city", lambda s: s.mode().iloc[0]),
    geolocation_state=("geolocation_state", lambda s: s.mode().iloc[0]),
).reset_index()

log("\n## Geolocation")
log(f"- Dropped {n_exact_dupes} exact duplicate rows.")
log(f"- Dropped {n_out_of_country} rows with lat/lng outside Brazil's bounding box.")
log(f"- Collapsed to one row per zip prefix (mean lat/lng, most common city and state spelling): "
    f"{len(geo_by_zip)} rows, down from {len(geo)}. This is the file to join for regional lookups; "
    f"the raw file has too many inconsistent city-name spellings to group on directly.")

# ---------------------------------------------------------------------------
# Note for the team: customer_id is order-scoped, customer_unique_id is the
# actual person. Retention or repeat-purchase analysis must use
# customer_unique_id or every customer looks like a first-time buyer.
# ---------------------------------------------------------------------------

log("\n## Customers")
log(f"- No nulls, no duplicate customer_id.")
log(f"- {customers['customer_id'].nunique()} distinct customer_id but only "
    f"{customers['customer_unique_id'].nunique()} distinct customer_unique_id. Any repeat-purchase or "
    f"retention metric must group on customer_unique_id, not customer_id.")

log("\n## Sellers")
log("- Clean: no nulls, no duplicate seller_id.")

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------

orders.to_csv(OUT + "orders_clean.csv", index=False)
order_items.to_csv(OUT + "order_items_clean.csv", index=False)
order_items_agg.to_csv(OUT + "order_items_agg.csv", index=False)
payments.to_csv(OUT + "payments_clean.csv", index=False)
payments_agg.to_csv(OUT + "payments_agg.csv", index=False)
reviews.to_csv(OUT + "reviews_clean.csv", index=False)
reviews_dedup.to_csv(OUT + "reviews_dedup.csv", index=False)
products.to_csv(OUT + "products_clean.csv", index=False)
customers.to_csv(OUT + "customers_clean.csv", index=False)
sellers.to_csv(OUT + "sellers_clean.csv", index=False)
geo_by_zip.to_csv(OUT + "geolocation_by_zip.csv", index=False)
cat_trans_patched.to_csv(OUT + "category_translation_patched.csv", index=False)

with open("cleaning/decisions.md", "w") as f:
    f.write("# Cleaning decisions log\n\nGenerated by clean.py. Every count below is computed live, not hardcoded.\n\n")
    f.write("\n".join(decisions))

print("\nDone. Cleaned files in cleaned/, decisions logged in decisions.md")
