"""
Verification script for the Olist cleaning output.

Run after clean.py. Every check either passes or prints FAIL with the detail.
Exit code is non-zero if anything failed, so this can gate the Postgres load.
"""

import sys
import pandas as pd

RAW = "data/raw/"
CLEAN = "data/cleaned/"

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" :: {detail}" if detail else ""))
    if not condition:
        failures.append(name)


print("=" * 70)
print("ROW COUNTS")
print("=" * 70)

expected_rows = {
    "orders_clean.csv": 99441,
    "order_items_clean.csv": 112650,
    "order_items_agg.csv": 98666,
    "payments_clean.csv": 103886,
    "payments_agg.csv": 99440,
    "reviews_clean.csv": 99224,
    "reviews_dedup.csv": 98673,
    "products_clean.csv": 32951,
    "customers_clean.csv": 99441,
    "sellers_clean.csv": 3095,
    "geolocation_by_zip.csv": 19011,
    "category_translation_patched.csv": 73,
}
for fname, expected in expected_rows.items():
    actual = len(pd.read_csv(CLEAN + fname))
    check(f"{fname} row count", actual == expected, f"{actual} rows, expected {expected}")

print()
print("=" * 70)
print("GRAIN: files meant to be one row per order must be exactly that")
print("=" * 70)

for fname in ["order_items_agg.csv", "payments_agg.csv", "reviews_dedup.csv"]:
    df = pd.read_csv(CLEAN + fname)
    check(f"{fname} is one row per order_id", df["order_id"].duplicated().sum() == 0,
          f"{df['order_id'].duplicated().sum()} duplicate order_ids")

orders = pd.read_csv(CLEAN + "orders_clean.csv")
check("orders_clean is one row per order_id", orders["order_id"].duplicated().sum() == 0)

products = pd.read_csv(CLEAN + "products_clean.csv")
check("products_clean did not fan out in the category merge",
      products["product_id"].duplicated().sum() == 0,
      f"{len(products)} rows, {products['product_id'].nunique()} distinct product_id")

print()
print("=" * 70)
print("ZIP CODES: leading zeros preserved")
print("=" * 70)

for fname, col, expect_zero_prefixed in [
    ("customers_clean.csv", "customer_zip_code_prefix", 23995),
    ("sellers_clean.csv", "seller_zip_code_prefix", 1027),
]:
    df = pd.read_csv(CLEAN + fname, dtype={col: str})
    all_five = (df[col].str.len() == 5).all()
    n_zero = df[col].str.startswith("0").sum()
    check(f"{fname} {col} all 5 chars", all_five)
    check(f"{fname} {col} leading zeros intact", n_zero == expect_zero_prefixed,
          f"{n_zero} zip codes start with 0, expected {expect_zero_prefixed}")

print()
print("=" * 70)
print("CATEGORY TRANSLATION: the patched pair is mapped correctly")
print("=" * 70)

ct = pd.read_csv(CLEAN + "category_translation_patched.csv")
mapping = dict(zip(ct["product_category_name"], ct["product_category_name_english"]))
check("pc_gamer maps to pc_gamer", mapping.get("pc_gamer") == "pc_gamer",
      f"got {mapping.get('pc_gamer')!r}")
check("portateis_cozinha... maps to kitchen_portables",
      mapping.get("portateis_cozinha_e_preparadores_de_alimentos") == "kitchen_portables",
      f"got {mapping.get('portateis_cozinha_e_preparadores_de_alimentos')!r}")
check("no product category is left unmapped",
      products["product_category_name_english"].notnull().all())

print()
print("=" * 70)
print("DELIVERY LOGIC")
print("=" * 70)

check("valid_for_delay_calc excludes exactly the 1390 flagged rows",
      (~orders["valid_for_delay_calc"]).sum() == 1390,
      f"{(~orders['valid_for_delay_calc']).sum()} excluded")
check("delivered-but-no-date flag count is 8",
      orders["flag_delivered_but_no_date"].sum() == 8)
check("carrier-before-approved flag count is 1359",
      orders["flag_carrier_before_approved"].sum() == 1359)
check("customer-before-carrier flag count is 23",
      orders["flag_customer_before_carrier"].sum() == 23)

null_days_late = orders["days_late"].isnull()
check("days_late is null only where there is no delivery date",
      (null_days_late == orders["order_delivered_customer_date"].isnull()).all())
check("delivery_status is null exactly where days_late is null",
      (orders["delivery_status"].isnull() == null_days_late).all())
check("every non-null delivery_status is late or on_time",
      set(orders["delivery_status"].dropna().unique()) <= {"late", "on_time"})
check("late means days_late > 0, no off-by-one",
      (orders.loc[orders["delivery_status"] == "late", "days_late"] > 0).all())
check("on_time means days_late <= 0",
      (orders.loc[orders["delivery_status"] == "on_time", "days_late"] <= 0).all())

print()
print("=" * 70)
print("AGGREGATES MATCH THEIR SOURCE TABLES")
print("=" * 70)

items_raw = pd.read_csv(CLEAN + "order_items_clean.csv")
items_agg = pd.read_csv(CLEAN + "order_items_agg.csv")
check("order_items_agg total price equals item-level total",
      abs(items_agg["item_price_total"].sum() - items_raw["price"].sum()) < 0.01,
      f"agg {items_agg['item_price_total'].sum():.2f} vs raw {items_raw['price'].sum():.2f}")
check("order_items_agg total freight equals item-level total",
      abs(items_agg["freight_value_total"].sum() - items_raw["freight_value"].sum()) < 0.01)
check("order_items_agg n_items sums to item row count",
      items_agg["n_items"].sum() == len(items_raw))

pay_raw = pd.read_csv(CLEAN + "payments_clean.csv")
pay_agg = pd.read_csv(CLEAN + "payments_agg.csv")
check("payments_agg total equals payment-level total",
      abs(pay_agg["payment_value_total"].sum() - pay_raw["payment_value"].sum()) < 0.01)

print()
print("=" * 70)
print("FOREIGN KEYS STILL INTACT AFTER CLEANING")
print("=" * 70)

customers = pd.read_csv(CLEAN + "customers_clean.csv")
sellers = pd.read_csv(CLEAN + "sellers_clean.csv")
reviews_dedup = pd.read_csv(CLEAN + "reviews_dedup.csv")

check("orders.customer_id all present in customers",
      orders["customer_id"].isin(customers["customer_id"]).all())
check("order_items.order_id all present in orders",
      items_raw["order_id"].isin(orders["order_id"]).all())
check("order_items.product_id all present in products",
      items_raw["product_id"].isin(products["product_id"]).all())
check("order_items.seller_id all present in sellers",
      items_raw["seller_id"].isin(sellers["seller_id"]).all())
check("reviews_dedup.order_id all present in orders",
      reviews_dedup["order_id"].isin(orders["order_id"]).all())

print()
print("=" * 70)
print("NOTHING WAS SILENTLY DROPPED FROM THE CORE TABLES")
print("=" * 70)

for raw_name, clean_name in [
    ("olist_orders_dataset.csv", "orders_clean.csv"),
    ("olist_order_items_dataset.csv", "order_items_clean.csv"),
    ("olist_customers_dataset.csv", "customers_clean.csv"),
    ("olist_sellers_dataset.csv", "sellers_clean.csv"),
    ("olist_products_dataset.csv", "products_clean.csv"),
    ("olist_order_payments_dataset.csv", "payments_clean.csv"),
    ("olist_order_reviews_dataset.csv", "reviews_clean.csv"),
]:
    n_raw = len(pd.read_csv(RAW + raw_name))
    n_clean = len(pd.read_csv(CLEAN + clean_name))
    check(f"{clean_name} keeps every raw row", n_raw == n_clean, f"raw {n_raw}, clean {n_clean}")

print()
print("=" * 70)
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
