# What to report on

This is the structure for the report, the deck, and the dashboard, with the
number that goes in each slot. Every number is in `docs/FINDINGS.md` and its
source export is named there.

The judging criterion is quantified problems with recommendations. So every
section has the same skeleton: the problem, the number, the recommendation.
Method and caveats go in a separate section at the end, not inline.

## Report structure

### 1. Introduction (half a page)

- What Olist is, in two sentences.
- Why this dataset: Zain did not supply one, no comparable local data is
  published, and the shape (orders, sellers, delivery promises, reviews,
  shipping) is the shape of any marketplace.
- What was done: cleaning with a documented audit, three analyses, a
  dashboard, and a recommendation for each.
- One sentence on scale: 99,441 orders, 3,095 sellers, two years.

### 2. Data and cleaning (one page)

- The nine tables and how they connect. The relationship table from
  `docs/SCHEMA.md` is enough.
- What was wrong and what was done, as a short table: issue, count, fix.
  Pull it from `cleaning/decisions.md`. Lead with the zip code leading zeros
  and the duplicate reviews because those are the two that would have
  silently broken everything.
- The rule: nothing was dropped, only flagged. State the judged-order count.

### 3. Scenario 1: late deliveries (one and a half pages)

Problem: 6.7% of orders arrive after the promised date.

Numbers, in this order:

1. 4.29 stars on time versus 2.27 late. Gap 2.02, interval 1.98 to 2.06.
2. Bad review (1 or 2 stars) 62.5% of late orders versus 9.3% on time.
3. The bucket table: it gets worse with every extra day.
4. R$ 949,935 of goods delivered late; about 3,383 excess bad reviews,
   labelled as a what-if.
5. Where: the Northeast rates, and Rio by volume.
6. When: November 2017 and March 2018.

Figures: `delivery_score_by_delay_bucket.png` is the one to show. The state
and month charts support it.

Recommendations:

- Capacity planning for known peaks.
- Regional delivery promises that reflect real transit times.
- Investigate Rio de Janeiro specifically.

### 4. Scenario 2: seller quality (one page)

Problem: a small set of sellers produces a disproportionate share of bad
reviews.

Numbers:

1. 811 sellers ranked; method in one sentence (lower bound of the bad-review
   share, so small samples cannot top the list).
2. Worst 20: 1.8% of orders, 5.2% of bad reviews, 40.9% bad share versus
   14.0%, 16.2% late versus 6.3%.
3. 15 of 20 are late-driven, 5 are product-driven.
4. R$ 265,000 of revenue at stake, 2.4% of the ranked total.

Figure: `sellers_worst_by_wilson.png`. The scatter is for the appendix.

Recommendations:

- Monthly seller scorecard using this ranking.
- Two-track intervention: shipping deadlines for the late ones, product
  review for the others.
- Delisting last.

### 5. Scenario 3: freight (one page)

Open with the caveat: no cost data, so this is freight as a share of price,
not margin.

Numbers:

1. 16.6% overall; 3.6% of items cost more to ship than to buy.
2. The price band table. Under R$ 25: 77.3% freight ratio, 26.5% freight
   above price.
3. Same-state 13.0% versus cross-state 18.3%; 63.8% of items cross a line.
4. The Northeast pays the most and has almost no local sellers.
5. Furniture as the category where the problem is bulk, not price.

Figure: `freight_ratio_by_price_band.png` is the one. Category and state
charts support.

Recommendations:

- Minimum order value or free-shipping threshold aimed at the cheap band.
- Seller recruitment or stock placement in the Northeast.
- Category-specific freight rules for furniture.

### 6. The connection (half a page)

The three findings are one story. The states that pay the most freight are
the states that wait the longest. The sellers with the worst reviews are
mostly the late ones. So the marketplace's core operational problem is
delivery from a Southeastern seller base to a national customer base, and it
shows up as bad reviews, bad sellers, and expensive shipping depending on
where you look.

### 7. What this means for Zain (half a page)

The methods transfer directly. Delivery promise versus actual becomes
service activation or installation promise versus actual. Seller quality
becomes agent, store, or partner quality. Freight burden becomes the cost of
serving distant governorates. Say which Zain datasets would be needed.

### 8. Method and limitations (one page, at the end)

- Association, not causation. Say it once, plainly.
- The three filters that define a judged order.
- Welch's t-test and the Wilson interval, one paragraph each, in plain
  language. `docs/ANALYSIS_DECISIONS.md` has the wording.
- What was not done: regression, real distances, retention.
- How the numbers were verified: independent recomputation, all checks pass.

### Appendix

- Full cleaning decisions table.
- The full state tables for delivery and freight.
- The worst 20 seller table.
- Olist attribution and licence note (CC BY-NC-SA 4.0, non-commercial).

## Deck structure (12 to 15 slides)

1. Title.
2. Why this dataset, one slide.
3. Data at a glance: the counts and the relationship diagram.
4. Cleaning: three issues that would have broken everything, and the rule.
5. Scenario 1 headline: the two stars.
6. Scenario 1 evidence: the bucket chart.
7. Scenario 1 where and when: one map or bar, one line.
8. Scenario 1 recommendation.
9. Scenario 2 headline and the worst-20 chart.
10. Scenario 2 recommendation, two tracks.
11. Scenario 3 headline: the price band chart.
12. Scenario 3 geography and recommendation.
13. The connection: one slide, three angles on the same story.
14. What this means for Zain.
15. Appendix: method, verification, attribution.

Each scenario headline slide has one number in large type and one sentence.
The recommendation slide has three bullets at most.

## Dashboard structure (three pages)

Each page ends on the quantified number and the recommendation. The
dashboard supports the argument; it is not the argument.

**Page 1: Delivery.** Source files `delivery_summary.csv`,
`delivery_by_bucket.csv`, `delivery_by_state.csv`, `delivery_by_month.csv`.
Cards: late rate, score on time, score late, gap. Charts: score by bucket
(bar), late rate by state (bar or map), late rate by month (line).

**Page 2: Sellers.** Source files `sellers_worst.csv`,
`sellers_comparison.csv`. Cards: ranked sellers, worst-20 bad share versus
others, worst-20 late rate versus others. Charts: worst 20 by lower bound
(bar), late rate versus bad share (scatter, from `sellers_ranked.csv`).
A table of the worst 20 with state and cause.

**Page 3: Freight.** Source files `freight_summary.csv`,
`freight_by_price_band.csv`, `freight_by_category.csv`, `freight_by_state.csv`,
`freight_same_vs_cross_state.csv`. Cards: overall ratio, share freight above
price, same-state versus cross-state. Charts: ratio by price band (bar),
worst categories (bar), by state (bar or map).

Column names in the exports are the contract. Build the dashboard against
them and do not rename.

## What not to report

- p-values. The intervals carry the information.
- The word "margin" anywhere in scenario 3.
- Any claim that lateness causes low scores. "Is associated with" or "is
  followed by".
- Retention or customer lifetime value. The data cannot support it.
- More than 20 sellers by name.
