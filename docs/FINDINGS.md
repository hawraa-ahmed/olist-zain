# Findings

Every number below is produced by the scripts in `analysis/` and checked by
`verify/verify_results.py`. The file each number comes from is named so you
can trace it.

Money is Brazilian reais (R$). "Judged orders" means delivered orders with
consistent timestamps and a review: 94,458 of the 99,441 in the dataset.

## Scenario 1: late deliveries hurt satisfaction, badly

Source: `delivery_summary.csv`, `delivery_by_bucket.csv`, `delivery_by_state.csv`, `delivery_by_month.csv`

- 6.7% of judged orders arrived after the promised date (6,357 of 94,458).
- On-time orders average **4.29 stars**. Late orders average **2.27 stars**.
- The gap is **2.02 stars**, 95% confidence interval 1.98 to 2.06. That interval is narrow because the sample is huge; the gap is not in doubt.
- A late order gets a 1 or 2 star review **62.5%** of the time. An on-time order, 9.3%. Roughly seven times more likely.
- It gets worse with every extra day: 1 to 3 days late averages 3.29 stars, 4 to 7 days 2.11, 8 to 14 days 1.67. Past two weeks it flattens at about 1.7 because there is nowhere lower to go.
- R$ 949,935 of merchandise was delivered late.
- If late orders had the on-time bad-review rate, there would be about **3,383 fewer 1 and 2 star reviews**. This is a what-if, not a measurement.

Where:

- The Northeast is worst. Alagoas 20.5% late (390 orders), Maranhão 17.4% (700), Sergipe 15.1%, Piauí 14.0%, Ceará 13.9% (1,254).
- Rio de Janeiro is the big one: 12.0% late on 12,074 orders. In absolute terms it produces more late orders than the whole Northeast.
- São Paulo, the largest market at 39,683 orders, is 4.5% late.

When:

- Two spikes. November 2017 hit 12.3% late (Black Friday volume: 7,236 orders, up from 4,446 the month before). February to March 2018 hit 14.0% then **18.7%**, the worst month in the data, and reviews that month averaged 3.81.
- Outside the spikes, lateness sits between 2% and 6%.

What to recommend:

- Capacity planning ahead of known peaks. The November spike was predictable and the March spike coincides with the post-carnival backlog.
- A regional delivery promise: quote longer estimated dates in the states that consistently miss them, since the damage comes from missing the promise, not from the absolute transit time.
- Rio de Janeiro deserves its own investigation because of the volume it carries.

## Scenario 2: a small set of sellers generates a disproportionate share of bad reviews

Source: `sellers_ranked.csv`, `sellers_worst.csv`, `sellers_comparison.csv`

- 3,095 sellers have at least one order. 811 have 20 or more reviewed orders and were ranked.
- Ranking is by the 95% lower bound of each seller's bad-review share (1 or 2 stars), using the Wilson interval, so a seller with few reviews cannot top the list on luck.
- The worst 20 sellers handle **1.8%** of ranked orders but produce **5.2%** of ranked bad reviews.
- Their bad-review share is **40.9%**, versus 14.0% for the other 791 ranked sellers.
- Their late rate is **16.2%**, versus 6.3%. Their cancellation rate is 1.1%, versus 0.3%.
- They carry R$ 264,879 of merchandise across 1,608 orders.
- The rank 1 seller has 114 reviewed orders and 70 bad reviews: a 61% bad share, and the data is 95% sure it is at least 52%.
- 11 of the worst 20 are in São Paulo state, 4 in Paraná, 3 in Minas Gerais, 2 in Santa Catarina.

Is it lateness or the product?

- Across ranked sellers, late rate and bad-review share correlate at 0.53. Lateness explains a good part of seller quality, not all of it.
- 15 of the worst 20 have a late rate more than double the median. For them, the fix is logistics.
- 5 of the worst 20 have a normal late rate and still a high bad share. For them, the problem is what is in the box.

What to recommend:

- A seller scorecard using this exact ranking, reviewed monthly.
- A two-track intervention: the 15 with high lateness get a shipping deadline and a warning; the 5 with normal lateness get a product-quality review.
- Delisting is the last step, not the first. These sellers are small, so removing them costs little revenue, but the scorecard is the reusable asset.

## Scenario 3: freight is a tax on cheap items and distant states

Source: `freight_summary.csv`, `freight_by_category.csv`, `freight_by_price_band.csv`, `freight_by_state.csv`, `freight_same_vs_cross_state.csv`

The caveat first: the dataset has no product cost, so none of this is profit
margin. Freight ratio is freight divided by item price. It is a measure of
how much the customer pays on top, and therefore of conversion risk.

- Across 110,197 delivered items, freight is **16.6%** of item price in total (R$ 2.20 million freight on R$ 13.22 million of goods).
- The median item has a freight ratio of 23.2%, higher than the total because cheap items are numerous.
- **3.6%** of items cost more to ship than to buy.

By price:

- Items under R$ 25: freight is **77.3%** of price, and **26.5%** of them cost more to ship than to buy. 13,152 items.
- R$ 25 to 50: 39.7%.
- R$ 50 to 100: 23.9%.
- R$ 100 to 200: 16.1%.
- R$ 200 and up: 7.7%.

By category (45 categories with at least 200 items):

- Worst: electronics 29.5% (and 22% of electronics items have freight above price), food and drink 29.4%, living room furniture 26.3%, office furniture 25.0%, furniture and decor 23.7% on 8,160 items.
- Best: agro industry 8.0%, fixed telephony 8.1%, small appliances 8.4%, watches and gifts 8.4%.
- The pattern is average item price. Cheap categories have high ratios. Bulky categories with mid prices (furniture) are the exception worth acting on.

By geography:

- 63.8% of delivered items crossed a state line.
- Same-state shipping runs at 13.0% of price; cross-state at 18.3%. Average freight per item: R$ 13.45 versus R$ 23.63.
- Northern and Northeastern states pay the most: Maranhão 26.3%, Rondônia 24.7%, Sergipe 24.2%, Piauí 24.2%. In each of these, fewer than 2% of items come from a seller in the same state.
- The seller base is concentrated in the Southeast, so the North and Northeast import nearly everything.

What to recommend:

- A minimum order value or free-shipping threshold aimed at the under-R$ 25 band, where freight already exceeds price a quarter of the time. Bundling two cheap items halves the ratio.
- Regional fulfilment or seller recruitment in the Northeast, since the cross-state penalty is about 40% higher freight per real of goods.
- Category-specific freight rules for furniture, where the problem is volume, not price.

## The shape of the whole argument

Scenarios 1 and 3 share a geography: the states that pay the most freight are
the states that wait the longest. Scenario 2 connects to scenario 1: most bad
sellers are bad because they are late. So the three findings are one story
told from three angles, and the deck should say so.
