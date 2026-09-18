# Dataset schema

Olist is a Brazilian marketplace. A customer places an order on Olist's store;
the order contains items from one or more independent sellers; each seller
ships their items; the customer reviews the order once it arrives. Nine CSV
files describe this. The cleaned versions add a few derived columns and split
three tables into two grains each.

Money is in Brazilian reais (R$). Dates run from September 2016 to October 2018.

## How the tables connect

Read each row as: the child column points at the parent column. "One to many"
means one parent row can have several child rows.

| Child table | Child column | Parent table | Parent column | Cardinality |
|---|---|---|---|---|
| orders | customer_id | customers | customer_id | one to one |
| order_items | order_id | orders | order_id | one to many |
| order_items | product_id | products | product_id | one to many |
| order_items | seller_id | sellers | seller_id | one to many |
| order_payments | order_id | orders | order_id | one to many |
| order_reviews | order_id | orders | order_id | one to many, see note |
| products | product_category_name | category_translation | product_category_name | one to many |
| customers | customer_zip_code_prefix | geolocation | geolocation_zip_code_prefix | many to many |
| sellers | seller_zip_code_prefix | geolocation | geolocation_zip_code_prefix | many to many |

The centre of the model is `orders`. Everything either hangs off an order or
describes a party to one.

Three tables have more than one row per order: `order_items`,
`order_payments`, and `order_reviews`. Joining any of them directly to `orders`
multiplies the order rows. That is why the cleaned data provides an order-grain
version of each.

The odd one is `order_reviews`. In principle one review per order, but 551
orders have two or more, and 789 `review_id` values are shared across
different orders. Neither column is a usable key in the raw file.

## Grain of each table

"Grain" means: what does one row represent.

| Table | One row is | Rows (raw) |
|---|---|---|
| orders | one order | 99,441 |
| customers | one order's customer record | 99,441 |
| sellers | one seller | 3,095 |
| products | one product | 32,951 |
| order_items | one item line in an order | 112,650 |
| order_payments | one payment attempt on an order | 103,886 |
| order_reviews | one review submission | 99,224 |
| geolocation | one geocoded point for a zip prefix | 1,000,163 |
| category_translation | one Portuguese to English category pair | 71 |

## Raw tables, column by column

### orders

| Column | Type | Meaning |
|---|---|---|
| order_id | text, 32 hex chars | Unique order identifier. Primary key. |
| customer_id | text, 32 hex chars | Points at customers. One per order. |
| order_status | text | One of: delivered, shipped, canceled, unavailable, invoiced, processing, created, approved. 97% are delivered. |
| order_purchase_timestamp | timestamp | When the customer placed the order. Never null. |
| order_approved_at | timestamp | When payment was approved. 160 nulls. |
| order_delivered_carrier_date | timestamp | When the seller handed the parcel to the carrier. 1,783 nulls. |
| order_delivered_customer_date | timestamp | When the customer received it. 2,965 nulls, almost all non-delivered orders. |
| order_estimated_delivery_date | timestamp at midnight | The delivery date promised at purchase. Never null. This is the "promise" that lateness is measured against. |

### customers

| Column | Type | Meaning |
|---|---|---|
| customer_id | text | Primary key. Scoped to a single order: a person who orders twice gets two of these. |
| customer_unique_id | text | The actual person. 96,096 distinct values versus 99,441 customer_id. Use this for any repeat-purchase question. |
| customer_zip_code_prefix | text, 5 digits | First five digits of the postcode. Has leading zeros. Must be loaded as text. |
| customer_city | text | Lower case, no accents. |
| customer_state | text, 2 letters | Brazilian state code. 27 values. Never null. Use this for regional analysis rather than joining geolocation. |

### sellers

| Column | Type | Meaning |
|---|---|---|
| seller_id | text | Primary key. |
| seller_zip_code_prefix | text, 5 digits | Same leading-zero warning as customers. |
| seller_city | text | |
| seller_state | text, 2 letters | 23 values. |

### products

| Column | Type | Meaning |
|---|---|---|
| product_id | text | Primary key. |
| product_category_name | text, Portuguese | 610 nulls in raw. 73 distinct values. |
| product_name_lenght | integer | Length of the product title. Spelled with the dataset's typo. 610 nulls, same rows as category. |
| product_description_lenght | integer | Same. |
| product_photos_qty | integer | Same. |
| product_weight_g | float | 2 nulls. |
| product_length_cm | float | 2 nulls. |
| product_height_cm | float | 2 nulls. |
| product_width_cm | float | 2 nulls. |

### order_items

| Column | Type | Meaning |
|---|---|---|
| order_id | text | Points at orders. |
| order_item_id | integer | 1, 2, 3 within the order. Together with order_id forms the primary key. |
| product_id | text | Points at products. |
| seller_id | text | Points at sellers. One order can have items from several sellers. |
| shipping_limit_date | timestamp | The date by which the seller must hand over to the carrier. Not used in this project. |
| price | float | Item price in R$. Always positive. |
| freight_value | float | Shipping charged for this item in R$. 383 zeros. |

### order_payments

| Column | Type | Meaning |
|---|---|---|
| order_id | text | Points at orders. |
| payment_sequential | integer | 1, 2, 3 within the order. An order paid with two vouchers has two rows. |
| payment_type | text | credit_card, boleto, voucher, debit_card, not_defined (3 rows). |
| payment_installments | integer | Number of instalments. 2 zeros. |
| payment_value | float | Amount in R$. 9 zeros, mostly vouchers. |

### order_reviews

| Column | Type | Meaning |
|---|---|---|
| review_id | text | Not unique. 789 values reused across different orders. Never join on it. |
| order_id | text | Points at orders. 551 orders have more than one row. |
| review_score | integer, 1 to 5 | The rating. Never null. |
| review_comment_title | text | 88% null. |
| review_comment_message | text | 59% null. Portuguese. |
| review_creation_date | timestamp | When the survey was sent. |
| review_answer_timestamp | timestamp | When the customer answered. Used to pick the latest review when there are several. |

### geolocation

| Column | Type | Meaning |
|---|---|---|
| geolocation_zip_code_prefix | text, 5 digits | Leading zeros. Not unique: many points per prefix. |
| geolocation_lat | float | |
| geolocation_lng | float | |
| geolocation_city | text | Inconsistent spelling in raw. |
| geolocation_state | text, 2 letters | |

### category_translation

| Column | Type | Meaning |
|---|---|---|
| product_category_name | text | Portuguese. Primary key. |
| product_category_name_english | text | English. |

Raw has 71 rows. Two categories used in products are missing:
`pc_gamer` and `portateis_cozinha_e_preparadores_de_alimentos`.

## Cleaned files

Twelve files. Nine are the raw tables with fixes applied and every raw row
kept. Three are extra: order-grain versions of the three many-per-order tables.

| File | Rows | What changed from raw |
|---|---|---|
| orders_clean.csv | 99,441 | Six columns added, see below. No rows dropped. |
| customers_clean.csv | 99,441 | Zip as zero-padded text. |
| sellers_clean.csv | 3,095 | Zip as zero-padded text. |
| products_clean.csv | 32,951 | Two columns added: `product_category_name_english` (from the patched translation table, "unknown" where the category was null) and `flag_missing_category`. |
| order_items_clean.csv | 112,650 | Unchanged. |
| order_items_agg.csv | 98,666 | New. One row per order: `n_items`, `item_price_total`, `freight_value_total`, `n_distinct_sellers`. |
| payments_clean.csv | 103,886 | Two flag columns: `flag_zero_value`, `flag_undefined_type`. |
| payments_agg.csv | 99,440 | New. One row per order: `payment_value_total`, `max_installments`, `n_payment_rows`. |
| reviews_clean.csv | 99,224 | Unchanged. Still has the duplicates. |
| reviews_dedup.csv | 98,673 | New. One row per order, the review with the latest `review_answer_timestamp`. This is the file to join to orders. |
| geolocation_by_zip.csv | 19,011 | Collapsed to one row per zip prefix: mean lat and lng, most common city and state spelling. Exact duplicates and 27 out-of-Brazil points removed first. |
| category_translation_patched.csv | 73 | Two rows added for the missing categories. |

### Columns added to orders_clean

| Column | Type | Meaning |
|---|---|---|
| flag_delivered_but_no_date | boolean | Status is delivered but no delivery timestamp. 8 rows. |
| flag_carrier_before_approved | boolean | Carrier pickup logged before payment approval. 1,359 rows. |
| flag_customer_before_carrier | boolean | Customer received before carrier pickup. 23 rows. |
| valid_for_delay_calc | boolean | None of the three flags is set. 98,051 rows. Every delivery-timing number in the project filters on this. |
| days_late | float, may be null | Days between delivery and the estimated date. Negative means early. Null where there is no delivery date. |
| delivery_status | text, may be null | "late" if days_late is above 0, "on_time" otherwise, null where days_late is null. |

Because `order_estimated_delivery_date` is always midnight, `days_late` above
0 means the parcel arrived on a later calendar date than promised. Arriving at
23:00 on the promised day counts as on time.

## Things that look like errors and are not

- `customer_id` not matching `customer_unique_id` counts: by design.
- `order_items` having more rows than `orders`: multi-item orders.
- 383 items with zero freight: plausible, kept.
- 88% of review titles null: most people do not write one.
- 2,957 of the 2,965 null delivery dates: orders that were never delivered.
