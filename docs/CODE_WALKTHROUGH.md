# Code walkthrough

Every line of the three analysis scripts, in order, with what it does and
why it is there. The scripts and the notebooks are the same code; the
notebooks are generated from the scripts by `tools/make_notebooks.py`.

Read this next to the notebook. Each heading matches a notebook section.

## Polars vocabulary used

These are the only Polars ideas in the project. If you know these, you can
read all of it.

- `pl.read_csv(path)` reads a file into a DataFrame. `try_parse_dates=True`
  turns date-looking text into real Datetime. `schema_overrides={col: pl.String}`
  forces one column to stay text (needed for zip codes).
- `df.shape` is (rows, columns). `df.schema` lists column types. `df.head(n)`
  shows the first n rows. `df.height` is the row count as a number.
- `df["col"]` pulls one column out as a Series. `.mean()`, `.sum()`,
  `.median()`, `.to_list()`, `.to_numpy()` work on a Series.
- `pl.col("name")` refers to a column inside an expression. Expressions are
  recipes; nothing runs until they are handed to `select`, `filter`,
  `with_columns`, or `agg`.
- `df.filter(condition)` keeps rows where the condition is true. Combine
  conditions with `&` (and), `|` (or), `~` (not), each in its own brackets.
- `df.with_columns(expr.alias("new"))` adds or replaces a column. The
  DataFrame is not changed in place; you must write `df = df.with_columns(...)`.
- `df.join(other, on="key", how="left")` matches rows by key. `left` keeps
  every row of `df` and fills unmatched columns with null.
- `df.group_by("col").agg(...)` splits into groups and computes one row per
  group. `pl.len()` counts rows in the group.
- `pl.when(cond).then(a).when(cond2).then(b).otherwise(c)` is if / elif / else
  as an expression. `pl.lit("x")` means the literal text "x", not a column
  named x.
- `df.sort("col", descending=True)` sorts. `df.with_row_index("rank", offset=1)`
  adds 1, 2, 3.
- `df.write_csv(path)` saves.

---

# analysis/01_delivery.py

## Imports and display

```python
import polars as pl
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
```

- `polars as pl`: the table library, shortened to `pl` so every call is short.
- `from scipy import stats`: one function is used, `ttest_ind`, for the
  confidence interval on the score gap.
- `matplotlib.use("Agg")` tells matplotlib to draw into files, not a window.
  Without it, running the script on a machine with no display can crash.
  It must come before `pyplot` is imported.
- `matplotlib.pyplot as plt`: the plotting interface.

```python
pl.Config.set_tbl_rows(30)
pl.Config.set_tbl_cols(-1)
pl.Config.set_tbl_width_chars(200)
pl.Config.set_fmt_str_lengths(14)
```

Display only. Show up to 30 rows, all columns, wide tables, and cut long
text (the 32-character ids) to 14 characters on screen. The data is not
touched. Same four lines as the reference notebook.

## 1. Load

```python
orders = pl.read_csv("data/cleaned/orders_clean.csv", try_parse_dates=True)
reviews = pl.read_csv("data/cleaned/reviews_dedup.csv", try_parse_dates=True)
items = pl.read_csv("data/cleaned/order_items_agg.csv")
customers = pl.read_csv("data/cleaned/customers_clean.csv",
                        schema_overrides={"customer_zip_code_prefix": pl.String})
```

- `orders`: `try_parse_dates=True` so the five timestamp columns come in as
  Datetime. Without it they are text and cannot be subtracted or sorted by
  time.
- `reviews`: the deduplicated file, one row per order. This is the only
  reviews file that may be joined to orders.
- `items`: the order-grain aggregate, one row per order with the price total.
  Not the item-level file, which would multiply rows.
- `customers`: `schema_overrides` keeps the zip column as text. Polars would
  otherwise read "01151" as the number 1151. The zip is not used in this
  script but the override is there so the file is loaded correctly every
  time; forgetting it once is how the bug gets in.

```python
orders.shape, reviews.shape, items.shape, customers.shape
```

Four (rows, cols) pairs. Expect (99441, 14), (98673, 7), (98666, 5),
(99441, 5). If any differs, the wrong file is in `data/cleaned/`.

```python
orders.schema
```

Confirms the timestamps parsed as Datetime and the flags as Boolean.

## 2. Keep only orders we can judge

```python
orders["order_status"].value_counts().sort("count", descending=True)
```

The status breakdown. 96,478 delivered. This is a look before filtering.

```python
delivered = orders.filter(
    (pl.col("order_status") == "delivered")
    & pl.col("valid_for_delay_calc")
    & pl.col("order_delivered_customer_date").is_not_null()
)
delivered.shape
```

Three conditions joined with `&`, each in brackets because `&` binds tighter
than `==`.

- Status delivered: only delivered orders have an arrival to compare.
- `valid_for_delay_calc`: a Boolean column from cleaning. True when none of
  the three timestamp-contradiction flags is set. Using a Boolean column
  directly as a condition is fine; no `== True` needed.
- Delivery date not null: 8 delivered orders have none.

Result: 95,097 rows. The comment on that line records the expected number.

## 3. Attach the review and the order value

```python
delivered = delivered.join(reviews.select("order_id", "review_score"), on="order_id", how="left")
delivered = delivered.join(items.select("order_id", "item_price_total", "freight_value_total"), on="order_id", how="left")
delivered.shape
```

- `.select("order_id", "review_score")` takes only the columns needed before
  joining, so the result does not fill up with review text and timestamps.
- `how="left"` keeps every delivered order even if it has no review or no
  items. Unmatched columns become null.
- `.shape` afterwards must still be 95,097 rows. Both right-hand tables have
  one row per `order_id`, so the join cannot multiply. Printing the shape is
  the proof.

```python
delivered.filter(pl.col("review_score").is_null()).height
```

Counts orders with no review: 639. Recorded so the drop in the next line is
explained.

```python
judged = delivered.filter(pl.col("review_score").is_not_null())
judged.shape
```

`judged` is the working set for the rest of the script: 94,458 orders,
delivered, consistent, reviewed.

## 4. The headline

```python
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
```

The outer brackets let the chain break across lines without backslashes.

- `group_by("delivery_status")`: two groups, late and on_time.
- `pl.len()`: rows per group.
- `review_score.mean()`: the average star rating per group.
- `(review_score <= 2).mean()`: the comparison gives True/False per row;
  the mean of a Boolean column is the share of True. So this is the share of
  1-and-2 star reviews without a separate count and divide.
- Same trick for 1 star only.
- `item_price_total.sum()`: merchandise value per group.
- `.round(n)` on each so the table is readable.
- `.sort("delivery_status")`: late before on_time, alphabetically, so the
  order is stable across runs.

```python
late_rate = judged.filter(pl.col("delivery_status") == "late").height / judged.height
round(late_rate * 100, 2)
```

Late orders divided by all judged orders. `.height` gives the count as a
plain number so the division is Python arithmetic. 6.73%.

## 5. Is the gap real?

```python
late_scores = judged.filter(pl.col("delivery_status") == "late")["review_score"].to_numpy()
ontime_scores = judged.filter(pl.col("delivery_status") == "on_time")["review_score"].to_numpy()
len(late_scores), len(ontime_scores)
```

Scipy wants plain arrays, not Polars columns. `["review_score"]` pulls the
column, `.to_numpy()` converts. Two arrays: 6,357 late scores, 88,101
on-time.

```python
test = stats.ttest_ind(ontime_scores, late_scores, equal_var=False)
ci = test.confidence_interval(confidence_level=0.95)
gap = float(ontime_scores.mean() - late_scores.mean())
round(gap, 3), (round(ci.low, 3), round(ci.high, 3)), test.pvalue
```

- `ttest_ind(a, b, equal_var=False)`: Welch's t-test comparing the mean of
  `a` to the mean of `b`. `equal_var=False` means do not assume the two
  groups have the same spread. Order matters for the sign: on-time first, so
  a positive gap means on-time is higher.
- `.confidence_interval(0.95)`: the range the true difference of means
  probably lies in. `ci.low` and `ci.high` are the ends.
- `gap`: the observed difference, computed directly so it can be printed.
  `float()` turns the numpy number into a plain Python number.
- The p-value is shown but not reported; with this sample size it is
  effectively zero and says nothing about size.

Result: gap 2.021, interval 1.981 to 2.060.

## 6. Does it get worse the later it is?

```python
judged = judged.with_columns(
    pl.when(pl.col("days_late") <= 0).then(pl.lit("on time"))
    .when(pl.col("days_late") <= 3).then(pl.lit("1-3 days late"))
    .when(pl.col("days_late") <= 7).then(pl.lit("4-7 days late"))
    .when(pl.col("days_late") <= 14).then(pl.lit("8-14 days late"))
    .otherwise(pl.lit("15+ days late"))
    .alias("delay_bucket")
)
```

A `when` chain is evaluated top to bottom and stops at the first true
condition, so `<= 3` after `<= 0` means "between 1 and 3". `pl.lit` makes
the label a literal string. `.alias` names the new column.

```python
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
```

- `group_by` and `agg` as before, one row per bucket.
- The sorting problem: bucket labels do not sort in a useful order
  alphabetically ("15+" would come first). So `replace_strict` maps each
  label to a number 0 to 4 using the list, that number goes in a temporary
  column `order_key`, the table is sorted on it, then the column is dropped.
  `replace_strict` errors if a label is not in the list, which is wanted:
  a typo in a bucket label should fail loudly.

## 7. Where is it happening?

```python
judged = judged.join(customers.select("customer_id", "customer_state"), on="customer_id", how="left")
```

Brings in the two-letter state. One customer row per order, so no fan-out.

```python
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
```

- `(delivery_status == "late").mean()`: share of late orders per state, same
  Boolean-mean trick.
- `days_late.filter(delivery_status == "late").mean()`: a filter inside an
  aggregation. Averages `days_late` over late orders only, within each state.
  Without the filter the average would include the negative early-arrival
  days and be meaningless.
- Sorted worst first. The `orders` column stays beside every rate so a
  40-order state is visibly different from a 40,000-order one.

## 8. When is it happening?

```python
by_month = (
    judged.with_columns(pl.col("order_purchase_timestamp").dt.strftime("%Y-%m").alias("month"))
    .group_by("month")
    .agg(
        pl.len().alias("orders"),
        (pl.col("delivery_status") == "late").mean().round(4).alias("late_rate"),
        pl.col("review_score").mean().round(3).alias("mean_score"),
    )
    .sort("month")
    .filter(pl.col("orders") >= 100)
)
by_month
```

- `.dt.strftime("%Y-%m")` turns a Datetime into text like "2017-11". `.dt`
  is the namespace for date operations; it only works because the column
  was parsed as Datetime at load.
- Text in that format sorts correctly, so `.sort("month")` gives time order.
- `.filter(orders >= 100)` after sorting drops the partial first and last
  months. 21 months remain.

## 9. Business impact

```python
late = judged.filter(pl.col("delivery_status") == "late")
late_revenue = late["item_price_total"].sum()
ontime_bad_rate = (judged.filter(pl.col("delivery_status") == "on_time")["review_score"] <= 2).mean()
late_bad_actual = (late["review_score"] <= 2).sum()
late_bad_expected = late.height * ontime_bad_rate
excess_bad_reviews = late_bad_actual - late_bad_expected
round(late_revenue, 2), late_bad_actual, round(late_bad_expected), round(excess_bad_reviews)
```

- `late`: the late subset, reused below.
- `late_revenue`: sum of merchandise value on late orders. R$ 949,935.
- `ontime_bad_rate`: share of on-time orders with a bad review. Here the
  comparison is done on a Series (`["review_score"] <= 2`) rather than in an
  expression; same result, both styles appear in the reference notebook.
- `late_bad_actual`: `.sum()` of a Boolean Series counts the Trues. 3,972.
- `late_bad_expected`: what the count would be if late orders had the
  on-time rate. 6,357 times 0.0926, about 589.
- `excess_bad_reviews`: the difference, 3,383. This is the what-if number.

```python
impact = pl.DataFrame({
    "metric": [ ... ],
    "value": [ ... ],
})
impact
```

Builds a two-column table by hand from a dictionary: a list of metric names
and a list of values. Every value is wrapped in `float()` because a Polars
column must have one type, and mixing the integer `judged.height` with the
float `late_rate` would fail. This table is the summary export for the
dashboard.

## 10. Export

```python
impact.write_csv("outputs/exports/delivery_summary.csv")
by_bucket.write_csv("outputs/exports/delivery_by_bucket.csv")
by_state.write_csv("outputs/exports/delivery_by_state.csv")
by_month.write_csv("outputs/exports/delivery_by_month.csv")
```

Four files. The column names in them are the contract with the dashboard.

## 11. Figures

```python
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
```

The pattern every figure follows:

- `plt.subplots(figsize=(w, h))` creates a figure and an axes to draw on.
- `ax.bar(x_labels, heights)`: matplotlib wants plain lists, so each Polars
  column is converted with `.to_list()`.
- `set_ylim(1, 5)`: the score axis runs 1 to 5, the real range, so the bars
  are not exaggerated by a zero baseline that could never occur.
- `set_ylabel`, `set_title`: labels.
- The `for` loop writes the value above each bar. `enumerate` gives the
  position `i` and the value `v`; `ax.text(x, y, text)` places it.
  `f"{v:.2f}"` formats to two decimals. `ha="center"` centres it.
- `tight_layout()` stops labels from being clipped.
- `savefig(path, dpi=150)` writes the PNG. `plt.close()` frees the figure so
  the next one starts clean.

```python
top_states = by_state.head(15)
fig, ax = plt.subplots(figsize=(8, 5))
ax.barh(top_states["customer_state"].to_list(), (top_states["late_rate"] * 100).to_list(), color="#DD8452")
ax.invert_yaxis()
...
for i, (rate, n) in enumerate(zip(top_states["late_rate"].to_list(), top_states["orders"].to_list())):
    ax.text(rate * 100 + 0.3, i, f"n={n:,}", va="center", fontsize=8)
```

- `head(15)`: the 15 worst states, since `by_state` is already sorted.
- `barh`: horizontal bars, easier to read with text labels.
- `(late_rate * 100)`: multiply the Series before converting, to get
  percentages.
- `invert_yaxis()`: `barh` draws bottom to top; inverting puts the first row
  at the top.
- `zip` pairs each rate with its order count so the label can show `n=`,
  which keeps the small-sample states honest. `f"{n:,}"` puts thousands
  separators in.

```python
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.plot(by_month["month"].to_list(), (by_month["late_rate"] * 100).to_list(), marker="o", color="#C44E52")
...
ax.tick_params(axis="x", rotation=45)
```

A line chart. `marker="o"` puts a dot on each month. `rotation=45` tilts the
month labels so 21 of them fit.

```python
print("Scenario 1 done.")
print(f"  judged orders: ...")
```

A summary printed to the terminal so running the script from the command
line shows the headline without opening any file.

---

# analysis/02_sellers.py

## Imports, display, constants

Same imports as scenario 1 minus scipy. The Wilson bound is computed in
Polars directly.

```python
MIN_REVIEWED_ORDERS = 20
WORST_N = 20
```

Two knobs, at the top so they are easy to find and change. The first is the
floor for being ranked; the second is how many sellers the slide names.

## 1. Load

```python
items = pl.read_csv("data/cleaned/order_items_clean.csv")
orders = pl.read_csv("data/cleaned/orders_clean.csv", try_parse_dates=True)
reviews = pl.read_csv("data/cleaned/reviews_dedup.csv")
sellers = pl.read_csv("data/cleaned/sellers_clean.csv",
                      schema_overrides={"seller_zip_code_prefix": pl.String})
```

This script needs item grain, because `seller_id` lives on items, not on
orders. Zip override on sellers for the same reason as before.

## 2. One row per (seller, order)

```python
seller_orders = (
    items.group_by("seller_id", "order_id")
    .agg(
        pl.len().alias("n_items"),
        pl.col("price").sum().alias("revenue"),
        pl.col("freight_value").sum().alias("freight"),
    )
)
seller_orders.shape
```

`group_by` on two columns: one group per distinct (seller, order) pair. An
order with three items from seller A becomes one row with `n_items` 3 and
the summed price. This is the step that stops one review from being counted
three times. Result: fewer rows than the 112,650 items.

## 3. Attach status, delivery result, review

```python
seller_orders = seller_orders.join(
    orders.select("order_id", "order_status", "valid_for_delay_calc", "delivery_status"),
    on="order_id", how="left",
)
seller_orders = seller_orders.join(reviews.select("order_id", "review_score"), on="order_id", how="left")
seller_orders.shape
```

Two left joins on `order_id`, each against a one-row-per-order table.
Shape unchanged after both, and the line prints it.

```python
seller_orders = seller_orders.with_columns(
    (pl.col("review_score") <= 2).alias("is_bad_review"),
    (pl.col("order_status") == "canceled").alias("is_canceled"),
    (pl.col("delivery_status") == "late").alias("is_late"),
)
seller_orders.head(3)
```

Three Boolean columns from three comparisons. Where `review_score` is null
(no review), `is_bad_review` is null too, not False. That matters: a null is
skipped by `.sum()` and `.mean()`, so orders without a review do not count as
"not bad".

## 4. Aggregate to one row per seller

```python
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
```

- `orders`: distinct orders per seller.
- `reviewed_orders`: `is_not_null()` gives True per reviewed row, `.sum()`
  counts them. This is the `n` in the Wilson formula.
- `mean_score`: shown for readability, not used for ranking.
- `bad_reviews`: count of bad reviews. Nulls skipped.
- `canceled_orders`: count.
- `late_rate`: the mean of `is_late`, but only over rows that are delivered
  and have valid timestamps. The `.filter()` inside `agg` restricts the
  rows the mean is taken over, per group. A seller whose orders were mostly
  canceled gets a late rate from very few rows.
- `revenue`: summed price.
- The second `with_columns` computes the two shares from the counts. Done
  after `agg` because they divide two aggregated columns.

Result: 3,095 rows, one per seller.

```python
per_seller.sort("orders", descending=True).head(5)
```

A look at the biggest sellers, to check the table makes sense.

## 5. The trap this ranking avoids

```python
per_seller.filter(pl.col("bad_share") == 1.0).sort("reviewed_orders").select("seller_id", "reviewed_orders", "bad_reviews", "bad_share").head(8)
```

Sellers with a 100% bad share, sorted by how many reviews that is based on.
The top of the list is sellers with 1 review. This cell exists to show the
problem before the fix.

```python
per_seller.filter(pl.col("bad_share") == 1.0)["reviewed_orders"].value_counts().sort("reviewed_orders").head(6)
```

How many 100%-bad sellers have 1 review, 2 reviews, and so on.

## 6. Wilson lower bound

```python
z = 1.96
p = pl.col("bad_share")
n = pl.col("reviewed_orders")
wilson_low = (p + z**2 / (2 * n) - z * ((p * (1 - p) / n) + z**2 / (4 * n**2)).sqrt()) / (1 + z**2 / n)
```

- `z = 1.96` is the normal-distribution multiplier for 95% confidence.
- `p` and `n` are expression handles for the two columns, so the formula
  reads like the maths.
- `wilson_low` is an expression, not a number. Nothing is computed yet. It
  is the standard Wilson lower bound formula written term by term:
  numerator `p + z²/2n - z·√(p(1-p)/n + z²/4n²)`, denominator `1 + z²/n`.
  `**` is power, `.sqrt()` is square root on an expression.

```python
per_seller = per_seller.with_columns(wilson_low.round(4).alias("bad_share_lower_bound"))
per_seller.select("seller_id", "reviewed_orders", "bad_share", "bad_share_lower_bound").sort("bad_share_lower_bound", descending=True).head(5)
```

The expression is applied here, producing the column for every seller at
once. The preview shows the top 5 by the bound; notice they all have real
review counts, not 1 or 2.

## 7. Rank only sellers with enough reviews

```python
ranked = (
    per_seller.filter(pl.col("reviewed_orders") >= MIN_REVIEWED_ORDERS)
    .sort("bad_share_lower_bound", descending=True)
    .with_row_index("rank", offset=1)
)
ranked.shape
```

Filter to the floor, sort by the bound, add a rank column starting at 1.
811 rows.

```python
ranked = ranked.join(sellers.select("seller_id", "seller_state", "seller_city"), on="seller_id", how="left")
worst = ranked.head(WORST_N)
worst.select("rank", "seller_id", "seller_state", "reviewed_orders", "bad_share", "bad_share_lower_bound", "late_rate", "cancel_rate", "revenue")
```

Attach state and city for the slide, take the top 20, show the columns that
matter.

## 8. What do these sellers cost?

```python
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
```

A two-row table built by hand. Each list has two entries: the worst group,
then everyone else. `bad_share` and `cancel_rate` are pooled (sum of counts
divided by sum of denominators), which weights big sellers more. `late_rate`
is the simple mean of per-seller rates. Both are defensible; the pooled one
is what the slide uses.

```python
share_of_all_bad_reviews = worst["bad_reviews"].sum() / ranked["bad_reviews"].sum()
share_of_all_orders = worst["orders"].sum() / ranked["orders"].sum()
round(share_of_all_bad_reviews * 100, 1), round(share_of_all_orders * 100, 1)
```

The "1.8% of orders, 5.2% of bad reviews" pair.

## 9. Lateness or product?

```python
ranked.select(pl.corr("late_rate", "bad_share").alias("corr_late_vs_bad"))
```

Pearson correlation between the two rates across all ranked sellers. 0.53.

```python
worst.select("rank", "seller_id", "bad_share", "late_rate").with_columns(
    pl.when(pl.col("late_rate") > ranked["late_rate"].median() * 2).then(pl.lit("lateness"))
    .otherwise(pl.lit("product or service"))
    .alias("likely_cause")
)
```

Labels each of the worst 20. The threshold is twice the median late rate of
all ranked sellers; `ranked["late_rate"].median()` is a plain number pulled
from the Series, then used inside the expression.

## 10. Export

Three files: the full ranking, the worst 20, and the comparison table.

## 11. Figures

```python
ax.barh([f"#{r} ({s[:8]})" for r, s in zip(worst["rank"].to_list(), worst["seller_id"].to_list())],
        (worst["bad_share_lower_bound"] * 100).to_list(), color="#C44E52")
```

The y labels are built with a list comprehension: rank plus the first 8
characters of the seller id (`s[:8]`), so the bars are identifiable without
32-character labels.

```python
ax.scatter((ranked["late_rate"] * 100).to_list(), (ranked["bad_share"] * 100).to_list(),
           s=12, alpha=0.4, color="#4C72B0", label="ranked sellers")
ax.scatter((worst["late_rate"] * 100).to_list(), (worst["bad_share"] * 100).to_list(),
           s=40, color="#C44E52", label=f"worst {WORST_N}")
ax.legend()
```

Two scatter layers on the same axes: all ranked sellers small and
translucent (`alpha=0.4`), the worst 20 larger and red on top. `s` is marker
size. `legend()` uses the `label` from each call.

---

# analysis/03_freight.py

## Constants

```python
MIN_ITEMS_PER_GROUP = 200
```

A category or state needs this many items to be ranked.

## 1. Load

Five files. This script needs `products` for the category, and both
`customers` and `sellers` for the two states.

## 2. Keep delivered orders only

```python
items = items.join(orders.select("order_id", "order_status", "customer_id"), on="order_id", how="left")
items = items.filter(pl.col("order_status") == "delivered")
items.shape
```

Join brings status and `customer_id` onto every item. Filter keeps delivered.
110,197 items from 112,650. `customer_id` is carried because the customer
state is needed later and it lives on the customer table, reachable only
through the order.

## 3. Attach category, customer state, seller state

```python
items = items.join(products.select("product_id", "product_category_name_english"), on="product_id", how="left")
items = items.join(customers.select("customer_id", "customer_state"), on="customer_id", how="left")
items = items.join(sellers.select("seller_id", "seller_state"), on="seller_id", how="left")
items.shape
```

Three joins, each to a table with one row per key. Shape unchanged.

```python
items.select("product_category_name_english", "customer_state", "seller_state").null_count()
```

Confirms nothing came back null. Category is "unknown" rather than null for
the 610 products with no category, because cleaning filled it.

## 4. The metric

```python
items = items.with_columns(
    (pl.col("freight_value") / pl.col("price")).round(4).alias("freight_ratio"),
    (pl.col("freight_value") > pl.col("price")).alias("freight_exceeds_price"),
    (pl.col("seller_state") == pl.col("customer_state")).alias("same_state"),
)
```

Three per-item columns: the ratio, a Boolean for freight above price, and a
Boolean for same-state shipping.

```python
overall = pl.DataFrame({
    "metric": [...],
    "value": [
        float(items.height),
        round(float(items["price"].sum()), 2),
        round(float(items["freight_value"].sum()), 2),
        round(float(items["freight_value"].sum() / items["price"].sum()), 4),
        round(float(items["freight_ratio"].median()), 4),
        round(float(items["freight_exceeds_price"].mean()), 4),
    ],
})
```

The overall summary. Note the fourth value is sum over sum, the ratio of
totals, and the fifth is the median of per-item ratios. They differ (16.6%
versus 23.2%) and both are reported so the difference is visible.

## 5. By product category

```python
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
```

- Sums per category, then the ratio of sums in a second `with_columns`
  because it divides two aggregated columns.
- `enough_items`: a Boolean flag rather than a filter, so small categories
  stay in the export but are marked.
- The preview filters to flagged-true and shows the 15 worst.

```python
by_category.filter(pl.col("enough_items")).tail(5)
```

The 5 cheapest to ship, for contrast on the slide.

## 6. By price band

```python
items = items.with_columns(
    pl.when(pl.col("price") < 25).then(pl.lit("a. under 25"))
    ...
    .otherwise(pl.lit("e. 200 and up"))
    .alias("price_band")
)
```

Same `when` chain pattern. The labels are prefixed "a." to "e." so that
sorting alphabetically gives price order, a simpler trick than the
`replace_strict` used in scenario 1. The prefix is stripped for the chart.

```python
by_price_band = (
    items.group_by("price_band")
    .agg(...)
    .with_columns((pl.col("total_freight") / pl.col("total_price")).round(4).alias("freight_ratio"))
    .sort("price_band")
)
```

Same shape as the category table.

## 7. By state, and same versus cross

```python
by_state = (
    items.group_by("customer_state")
    .agg(
        ...,
        pl.col("same_state").mean().round(4).alias("share_same_state_seller"),
    )
    ...
)
```

Adds the share of items that came from a same-state seller, per state.
This is the column that shows the North and Northeast have almost no local
supply.

```python
same_vs_cross = (
    items.group_by("same_state")
    .agg(...)
    .with_columns((pl.col("total_freight") / pl.col("total_price")).round(4).alias("freight_ratio"))
    .with_columns(pl.when(pl.col("same_state")).then(pl.lit("same state")).otherwise(pl.lit("cross state")).alias("route"))
    .select("route", "items", "total_price", "total_freight", "avg_freight", "freight_ratio")
    .sort("route")
)
```

Two rows. `pl.when(pl.col("same_state"))` uses the Boolean column directly
as the condition to make a readable label. `.select` reorders columns and
drops the raw Boolean.

```python
share_cross_state = 1 - items["same_state"].mean()
```

The mean of the Boolean is the same-state share; one minus it is the
cross-state share. 63.8%.

## 8 and 9. Export and figures

Five exports. Three figures following the same pattern as before. The only
new thing:

```python
labels = [b[3:] for b in by_price_band["price_band"].to_list()]
```

Strips the first three characters ("a. ") from each band label for the
chart axis.

---

# tools/make_notebooks.py

Splits each script on `# %%` and `# %% [markdown]` markers, builds a
notebook with nbformat, executes it with nbclient from the project root so
relative paths work, and writes it to `notebooks/`. The notebooks are
therefore always the same code as the scripts. Edit the script, rerun the
tool.

# verify/verify_results.py

Reads the cleaned CSVs with Python's built-in `csv` module and recomputes
every headline number using loops and dictionaries, then compares each to
the exported value. Lateness is recomputed from the raw timestamps by
comparing dates, not by reading `days_late`. The rank 1 seller's Wilson
bound is recomputed with scipy's implementation, not the hand-written
formula. If all checks pass, two independent implementations agree.
