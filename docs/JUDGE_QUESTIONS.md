# Questions a judge is likely to ask

Grouped by what they are probing for. The answer is what to say; the note
under it is where the evidence lives.

## Questions about the data

**Why a Brazilian dataset for a Zain hackathon?**
Zain did not supply data, and no comparable Iraqi e-commerce dataset is
published. Olist has the same shape as any marketplace: orders, sellers,
delivery promises, reviews, shipping cost. The methods transfer; the numbers
are a demonstration. The last slide should say what the same analysis would
show on Zain's own subscriber and service data.

**How big is it and how clean was it?**
99,441 orders, 3,095 sellers, 32,951 products, September 2016 to October
2018. It arrived mostly clean but with real traps: zip codes that lose their
leading zeros on load, reviews that are not one per order, timestamps that
contradict each other on 1,390 orders, and two categories missing from the
translation table. Every fix is in `cleaning/decisions.md` with a count.
Nothing was dropped, only flagged.

**Did you drop any orders?**
No. Every raw row is in the cleaned files. Analyses filter to the orders they
can judge and say how many that is: 94,458 for the delivery scenario, for
example, out of 99,441.

**What is the biggest thing that could have gone wrong?**
Joining reviews to orders without deduplicating. 551 orders have more than
one review; join naively and every number in scenario 1 is off. We collapsed
to one review per order (the latest) before any join, and the row count is
printed after every join to prove nothing multiplied.

## Questions about scenario 1

**Is a 2 star gap really that big?**
On a 5 point scale it is the difference between a 4.3 and a 2.3. In
practical terms, a late order gets a 1 or 2 star review 62% of the time
versus 9% for on-time. That is the number to lead with.

**How do you know it is the delay and not something else?**
We do not know it causally; this is observational data. What we can show is
dose-response: the score falls with every extra day late, 3.29 at 1 to 3
days, 2.11 at 4 to 7, 1.67 at 8 to 14. A confound would have to track the
number of days late, which is hard to explain any other way.
Source: `delivery_by_bucket.csv`.

**Why the 95% interval and what does it mean?**
The gap is 2.02 stars and the interval is 1.98 to 2.06. That means if you
reran this on another sample of the same population, you would expect the gap
to land in that range. It is narrow because we have 94,000 orders. The point
of showing it is that the effect is not just significant, it is large and
precisely measured.

**What counts as late?**
Arriving on a later calendar date than the estimated delivery date the
customer was shown at purchase. Same day counts as on time. 1,292 orders
arrived on the promised day.

**Why is Rio so bad?**
The data shows 12% late on 12,000 orders but does not say why. It is the
second largest market and has the worst rate among large markets. The
recommendation is to investigate it, not to explain it from this data.

**What happened in March 2018?**
18.7% of orders that month arrived late, the worst in the data, and reviews
averaged 3.81. It follows carnival and a February that was also bad. The
data does not identify the cause; volume was not unusual. Capacity or carrier
disruption are the likely candidates and the recommendation is to plan for
the pattern rather than diagnose the instance.

**Where does "3,383 excess bad reviews" come from?**
Late orders had 3,972 one-and-two star reviews. If they had the on-time bad
rate of 9.3%, they would have had about 589. The difference is 3,383. It is a
what-if, not a count, and the slide should label it as such.

## Questions about scenario 2

**How did you pick the worst sellers?**
Ranked by the lower bound of the 95% Wilson interval on their bad-review
share, with a floor of 20 reviewed orders. In plain terms: the sellers we are
most confident are bad, not the ones with the worst raw number.

**Why not just sort by average rating?**
Because the top of that list is sellers with two or three reviews who got
unlucky. A 3-review seller at 1.7 stars is not evidence. The lower bound
handles that automatically: fewer reviews, wider interval, lower bound closer
to zero.

**What is a Wilson interval?**
A confidence interval for a proportion that behaves well when the proportion
is near 0 or 1 or the sample is small, which is exactly the seller
situation. It is the standard choice for ranking by rating; the same idea is
used by review sites.

**Why 20 reviews minimum?**
811 sellers qualify at 20. At 10 the tail is noisy; at 50 you lose most of
the small sellers who are the ones causing problems. The threshold is a
constant in the script and the ranking can be regenerated at any value.

**Are the bad sellers bad because they are late?**
Mostly. Late rate and bad-review share correlate at 0.53 across ranked
sellers, and 15 of the worst 20 have a late rate more than double the median.
The other 5 have a normal late rate, so their problem is the product or the
service. That is why the recommendation has two tracks.

**How much revenue would you lose by removing them?**
R$ 265,000 across 1,608 orders, out of R$ 11.1 million across ranked
sellers. About 2.4%. The recommendation is a scorecard and a warning first,
delisting last, so the answer is "less than that, and only if they do not
improve".

**Did you check that the formula is right?**
Yes. `verify/verify_results.py` recomputes the rank 1 seller's bound with
scipy's own Wilson implementation and gets the same number to four decimals.

## Questions about scenario 3

**Is freight ratio the same as margin?**
No, and the report says so. There is no product cost in the data. Freight
divided by price is what the customer pays on top of the item. It tells you
about conversion risk and customer perception, not about profit.

**77% freight on cheap items, is that not just how shipping works?**
Partly, yes. Shipping a R$ 15 item costs about what shipping a R$ 150 item
costs. That is the point: the marketplace is selling 13,000 items a year
where the shipping is the larger line on the receipt, and a quarter of them
cost more to ship than to buy. A minimum order value or a bundling nudge is
the standard response.

**Why is the same-state versus cross-state comparison meaningful?**
63.8% of items cross a state line, and cross-state freight is 18.3% of price
versus 13.0% for same-state. The seller base is in the Southeast; the North
and Northeast import almost everything and pay the most. Recruiting sellers
or placing stock in the Northeast is the recommendation, and the data shows
where.

**Why ratio of sums rather than average ratio?**
Average of per-item ratios lets one R$ 5 item with R$ 15 freight (ratio 3.0)
distort a whole category. Sum of freight over sum of price weights every real
equally. The median item ratio is also reported, so both views are visible.

**Why only categories with 200 items?**
A category with 30 items has a ratio driven by a handful of products. 45 of
74 categories meet the floor and they cover almost all the volume.

## Questions about method

**Why Polars and not pandas or SQL?**
Polars is the team's shared tool from the Zain traineeship. The dataset is
small enough that any tool works. Scipy is used for confidence intervals
because Polars does not do inference.

**How do you know the numbers are right?**
Three layers. The cleaning has its own verification script. The analysis
prints row counts after every join. And `verify/verify_results.py`
recomputes every headline number with plain Python and the csv module, no
Polars, and compares. All 21 checks pass.

**What would you do with more time?**
A regression separating the effects of delay, seller, category, and state on
review score. Real distances from the geolocation table instead of same
state versus cross state. A retention analysis, which this dataset cannot
support because only 3% of customers return.

**Did you use AI tools?**
Yes, the rules allow it. The analysis code and this documentation were
produced with AI assistance and then reviewed, re-run, and independently
verified by the team. Every decision in `docs/ANALYSIS_DECISIONS.md` was
read and either accepted or changed by us.
