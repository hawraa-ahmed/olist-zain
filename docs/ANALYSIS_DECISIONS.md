# Analysis decisions

Every choice below could have gone another way. Each entry says what was
chosen, what the alternative was, and why. A judge who asks "why did you do X"
should find the answer here. Cleaning decisions are in
`cleaning/decisions.md`; this file covers the analysis only.

## Decisions that apply to all three scenarios

**Polars for tables, scipy for statistics, matplotlib for figures. No SQL.**
The team's shared tool is Polars. Postgres was in the original plan and was
dropped for time. Nothing here needs a database; the data is 45 MB.

**Aggregate before joining.** `order_items`, `order_payments`, and
`order_reviews` all have several rows per order. Every join to `orders` in
this project goes through a one-row-per-order version first
(`order_items_agg`, `reviews_dedup`, or a `group_by` inside the script).
Alternative: join the raw tables and deduplicate afterwards. Rejected because
it is the single most common way to inflate every number by a few percent
without noticing.

**Row counts printed after every join.** Each script shows `.shape` before
and after a join. If a join ever multiplies rows, it shows up there.

**Minimum group sizes.** Sellers need 20 reviewed orders to be ranked.
Categories and states need 200 items to be compared on freight. States are
shown in the delivery table regardless, with their order count beside them.
Alternative: no floor. Rejected because small groups produce extreme values
by chance and the slide would name the wrong things.

**Confidence intervals over p-values.** With 94,000 orders nearly any
difference is statistically significant. The interval says how big the
effect is; that is the business question.

## Scenario 1: delivery

**Late means arrived on a later calendar date than promised.** The estimated
date is always midnight, so `days_late > 0` is equivalent to comparing dates.
A parcel arriving at 23:00 on the promised day is on time. Alternative:
treat any arrival after 00:00 on the promised day as late, which would call
1,292 same-day deliveries late. Rejected because the customer was told a day,
not a time.

**Only delivered orders with consistent timestamps are judged.** Three
filters: status delivered, `valid_for_delay_calc` true, delivery date
present. This removes 1,390 orders with contradictory timestamps and 8 with
no date. Alternative: keep everything with a delivery date. Rejected because
an order whose carrier date is after its delivery date has at least one
wrong timestamp, and there is no way to know which.

**Orders with no review are dropped from the score analysis only.** 639
judged orders have no review. They are counted, then excluded, since there is
no score to average. They are not excluded from anything else.

**Welch's t-test, not Student's.** Welch does not assume the late and on-time
groups have the same spread, and they do not: late scores are far more
dispersed. Alternative: Mann-Whitney, which is more correct for a 1 to 5
ordinal scale. Not used because the interval on a mean difference is what
belongs on a slide, and with this sample size the two tests agree on
everything that matters.

**Delay buckets: on time, 1 to 3, 4 to 7, 8 to 14, 15+.** Chosen to be
readable. The last bucket is open-ended because the score flattens after two
weeks and finer splits there would just show noise.

**By state uses `customer_state` from the customers table, not the
geolocation join.** The state code is on every customer row already. Going
through geolocation would lose 279 customers whose zip has no match, for no
gain.

**Months with under 100 judged orders are dropped from the monthly table.**
This removes the partial first and last months. The remaining 21 months are
complete.

**"Excess bad reviews" is a what-if.** It assumes late orders would have had
the on-time bad-review rate if they had been on time. That is a reasonable
counterfactual but it is not observed, and the slide has to say so.

**Revenue delivered late uses item price only, not freight.** Freight is the
carrier's revenue, not the marketplace's merchandise value.

## Scenario 2: sellers

**One row per seller per order before anything else.** An order with three
items from one seller has one review, not three. Collapsing to
(seller, order) first means each review counts once per seller. Alternative:
work at item grain. Rejected; it would weight multi-item orders more heavily
for no reason.

**"Bad review" is 1 or 2 stars.** Alternative: 1 star only, or mean score.
Two stars is still a clearly unhappy customer; the 1-and-2 share is more
stable than the 1-only share for small sellers; and a proportion has a
well-known confidence interval (Wilson), which a mean on a 1 to 5 scale does
not have as cleanly.

**Rank by the Wilson lower bound of the bad-review share.** The lower bound
is the smallest bad share the data is 95% confident in. A seller with 2
reviews, both bad, has a raw share of 100% but a lower bound around 20%,
because two observations cannot rule out much. A seller with 60 reviews and
24 bad has a raw share of 40% and a lower bound around 29%, and ranks higher.
Alternative: rank by raw share with a minimum count. Also used as a floor,
but on its own it still lets a 20-review seller with a lucky streak outrank
a 200-review seller who is consistently mediocre.

**Why a lower bound and not an upper bound.** For a "worst" list we want
sellers whose bad share is certainly high. That is the lower bound of the bad
share. If the list were of best sellers, ranked on good share, it would also
be a lower bound. The bound is always on the side that makes the claim
conservative.

**The Wilson formula is written out in Polars rather than calling scipy per
seller.** Vectorised, and the formula is visible in the notebook so it can be
checked. `verify/verify_results.py` compares it to scipy's implementation on
the rank 1 seller and they agree to four decimals.

**Minimum 20 reviewed orders.** 811 sellers qualify. At 10 it would be 1,269
and the tail gets noisy; at 50 it would be 425 and small sellers with real
problems would be invisible. 20 is the compromise. It is a constant at the top
of the script and can be changed.

**Worst 20, not worst decile.** 10% of 811 is 81 sellers, which is a
spreadsheet, not a slide. 20 is a list a person can read. Also a constant.

**Late rate per seller is computed only on delivered orders with valid
timestamps.** Same rule as scenario 1, applied inside the seller
aggregation with a filter. Sellers whose orders were mostly canceled have a
late rate computed on very few orders; it is shown but should not be leaned
on.

**Cancellation rate is computed on orders that have items.** 164 canceled
orders have no item rows and therefore no seller. They cannot be attributed
and are not counted. Seller cancellation rates are therefore slightly
understated.

**"Likely cause" splits at twice the median late rate.** A seller above that
is called a lateness problem; below it, a product or service problem. The
threshold is a judgement. The correlation of 0.53 between late rate and bad
share is what justifies splitting at all.

## Scenario 3: freight

**Freight ratio, not margin.** The dataset has no cost of goods. Freight
divided by price is what the customer sees, and it is honest. The report must
not call it margin or profit.

**Delivered orders only.** A canceled order was quoted freight but the goods
never moved. The economics are about what actually shipped. This removes
about 2,400 items.

**Ratio of sums, not mean of ratios.** Category ratio is
sum(freight) / sum(price), not the average of each item's freight / price.
The mean of ratios lets one R$ 5 item with R$ 15 freight (ratio 3.0) pull the
whole category. The ratio of sums weights every real equally. The median
item ratio is also reported for the overall figure so the two views are both
visible.

**Price bands at 25, 50, 100, 200.** Round numbers that split the data into
five usable groups. The under-25 band is the one that matters and it holds
13,152 items.

**"Same state" means seller state equals customer state.** A crude proxy for
distance; the geolocation table would allow real distances. Not done because
the state split already shows the effect clearly and the extra precision
would not change the recommendation.

**Categories under 200 items are listed but flagged, not ranked.** The
`enough_items` column marks them. 45 of 74 categories qualify. The rest are
in the export for completeness.

**"Freight exceeds price" is a per-item flag.** It is the most concrete
number in the scenario: 3.6% of everything sold, and 26.5% of items under
R$ 25, cost more to ship than to buy. It needs no statistics to defend.

## What was not done, and why

- **No causal claims.** Every finding is an association in observational
  data. Late delivery is associated with low scores; the dataset cannot prove
  the delay caused the score. The report should use "associated with" and
  "is followed by", not "causes".
- **No retention analysis.** Only about 3% of customers order twice, so
  "late orders lose customers" cannot be tested here.
- **No regression.** A model predicting review score from delay, seller,
  category, and state would be the natural next step and would separate the
  three effects. Not done in the time available and not needed for the three
  recommendations.
- **No payments scenario.** Cancellations are 0.6% of orders; too thin.
