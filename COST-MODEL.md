# Strata cost model

Monthly AWS cost of Strata today and at 10× growth, for the chosen design (**B′**) and three alternatives, with every assumption stated.

- **Calculator:** [`cost_model.py`](cost_model.py). Run `python3 cost_model.py --update-doc`. Every results table below sits between `BEGIN`/`END` markers and is regenerated from the script, so the document can't drift from the code. 
- **Prices:** AWS list prices for **eu-west-1** (Ireland), from the AWS Price List API files published in September 2026, checked on 2026-10-05 and 2026-10-06. No free tier is counted. Sources: `research-aws-github.md` and `research-prices-euw1.md`.
- **Architecture:** [`ARCHITECTURE.md`](ARCHITECTURE.md) and the spine.
- **Revisions 2026-10-07:** final review: design D now scales with its workload, the largest repository is modeled on its own, and the lifecycle-gate dependency and a retention row are shown.
- **Earlier revision 2026-10-07:** after the Challenge review, added the lines it found missing and the hybrid design B′. Also: batch hours now scale with size, quiet-day cost is shown per day (COST-5), and at-risk data now keeps growing when nobody decides. The same day the product owner chose **B′** (AD-1 amended), so B′ is now the chosen design throughout.

## 1. Result

<!-- BEGIN:designs -->
| Design | Today | At 10× | 10× bill ÷ today's | Today vs B′ |
|---|---|---|---|---|
| **B′. Hybrid: daily batch job + Step Functions for restore and events (chosen)** | $9.58 | $54.64 | 5.7× | 1.00× |
| A. Orchestrated pipeline (Step Functions for everything) | $10.14 | $61.06 | 6.0× | 1.06× |
| B. Batch job, no Step Functions at all | $9.43 | $54.47 | 5.8× | 0.98× |
| D. Always-on Graviton VM | $24.28 | $57.94 | 2.4× | 2.53× |
<!-- END:designs -->

- **Meets the 10× rule (PRD SM-6):** at 10× the data, design B′'s bill grows 5.7×, within the "no more than 10×" limit.
- **Storage is not the cost.** All backup storage together (bases, additions, records) costs well under $0.50 a month today. What costs money is running Strata: capture compute, fixed security and monitoring items, and the workflow service.
- **Quiet days cost almost nothing.** See §6.

## 2. Why design B′, and what the numbers say about the alternatives

All four designs meet **every** requirement (PRD COST-1). They therefore share the whole vault side: Object Lock, notary, keeper, watchdog, tamper detection, both accounts, the per-push captures (FR-18 / AD-4) and email. They differ only in how the work is run.

- **B′ (chosen) vs A.** In B′, the daily run is one Fargate batch job using the same capture code, while Step Functions stays for restore, restore test and event handling. A keeps Step Functions for everything.
  - **Savings:** B′ is about **$0.55 a month cheaper today** and **$6.40 at 10×**.
  - **Trade-off:** B′ hand-builds the daily run's retries, parallel captures, rate pacing, 100% check and re-run rule, and uses two orchestration styles.
  - **Decision (product owner, AD-1 amended 2026-10-07):** B′, because it keeps the architecture simple without hand-building the multi-hour restore and event flows.
- **B (no Step Functions at all) vs B′.** B also hand-builds the restore (including the 12-hour Deep Archive wait), the restore test and event handling.
  - It saves only about **$0.16 a month more than B′ today** ($0.17 at 10×).
  - **Rejected by the product owner:** it adds custom orchestration just to save a very small amount.
- **D. Always-on Graviton VM.** A t4g.small today and a t4g.medium at 10×, with local disk and a public IPv4 address, doing all captures with caches on its own disk.
  - **Today:** it costs about **2.5 times as much** as B′ (see the "Today vs B′" column), because the machine is paid for every hour.
  - **At 10×:** which design wins depends on **how long a capture takes** (§7). The model now sizes D to its workload: as many instances as needed to keep each at or below 50% utilization, leaving headroom for FR-18's 15-minute start. The break-even is still about **22 seconds per capture**: below that, B′ stays cheaper at 10×; above it, one VM is cheaper until about 42 seconds, when D needs a second instance.
  - **Decision (product owner):** keep B′. It is within $0.16 a month of the cheapest design (B) and was chosen by the COST-1 tie-break (less custom code, fewer failure points). **Reconsider the Graviton VM when Orvex approaches 10× today's size.** At that point, compare using the capture duration *measured* in the build, and weigh the saving against a single machine to patch and keep alive, a single point of failure, and "serverless first".

## 3. Assumptions

"Product owner" means Maram decided it; "Claude, accepted" means Claude proposed it and Maram accepted it; "the Orvex contact" means it comes from the Orvex contact's guidance; "Claude (review)" marks assumptions added on 2026-10-07 to close Challenge-review gaps; the product owner **accepted** them the same day.

### 3.1 Workload

| # | Assumption | Value today | At 10× | Owner | Notes |
|---|---|---|---|---|---|
| W1 | Repositories | 93 | 930 | Orvex contact | |
| W2 | Git data | 4 GB | 40 GB | Orvex contact | Bundle size is taken as equal to Git data size. |
| W3 | Repositories changing on a given day | 30% (about 28), treated as a fixed **active set**; the other 70% are dormant | same share | Claude, accepted | Active repos are assumed to hold 30% of the data (about 43 MB each). |
| W4 | **Pushes per day** (each push is a capture, AD-4) | **200** | 2,000 | Product owner | **Sensitivity: 100 and 400.** |
| W5 | New Git data per push | 50 KB | 50 KB | Claude, accepted | Treated as all under 128 KB, so stored in S3 Standard (AD-3). |
| W6 | **Capture duration** (download cache, fetch, bundle, upload, claim) | **20 s at 2 GB memory**, 2 GB disk | same | Claude, accepted | **Sensitivity: 10 s and 40 s.** To be measured in the build. Decides B′ vs D at 10× (§7). |
| W7 | Daily-run check of an unchanged repository | 2 s at 2 GB | same | Claude | |
| W8 | Base rebuild (AD-25) | 30 s at 2 GB | same | Claude | |
| W9 | Largest repository | about 1 GB, modeled as its own **active** repository on top of the active set (conservative) | 1 GB | Claude, accepted; modeling choice from the final review | Fits Lambda (10 GB disk, 15 min), so event captures never need Fargate. Sensitivity: dormant. |
| W10 | Rewrite events | **1 a week** | 10 a week | Product owner | **High case: 20 a week.** |
| W11 | Deleted repositories (all content at-risk) | 2 a year | 20 a year | Claude (review) | |
| W12 | Restores | 1 monthly test + 1 real a month, about 200 MB read each | same | Claude, accepted | |
| W13 | Emails | **20 a day** | 200 a day | Product owner | **Burst case: 200 a day.** |
| W14 | LFS | **0 today** (Orvex contact) | 0 | Orvex contact / product owner | **Separate scenario:** 3 files of 5 GB, each changed weekly (about 65 GB a month). |

### 3.2 Design parameters

| # | Parameter | Value | Source |
|---|---|---|---|
| D1 | New base after this many days with changes | 7 | AD-2 (product owner) |
| D2 | Routine retention / at-risk retention | 1 year / 3 years; at-risk then auto-extended while nobody decides | Brief, AD-7 (product owner) |
| D3 | Records and audit retention | 3 years | AD-7 |
| D4 | Storage class | Bases, and additions and LFS objects ≥ 128 KB: Standard until verified, then Deep Archive. Smaller additions: Standard. Records: Standard. | AD-3, D-D (product owner) |
| D5 | Worker cache old versions kept | 1 day | Product owner |
| D6 | Records per capture | repository-state + capture records (about 5 KB) + 3 audit entries of 1 KB | Claude |
| D7 | Records per repository per daily run, even when unchanged | 2 (capture record + audit entry) | Claude (review) |
| D8 | Notary read-and-verify time | 0.05 s per MB, at 2 GB memory | Claude (review) |
| D9 | Keeper hold releases per retired chain | 10 requests | Claude (review) |
| D10 | Watchdog and vault escalation sweep | every 15 minutes each, about 3 s at 0.5 GB | AD-13, AD-27 |
| D11 | Batch parallelism (designs B, B′) | 4 captures at a time in the daily batch job | Claude (review) |
| D17 | Design D sizing | t4g instances with 2 vCPUs each, at most 50% utilization; small today, medium at 10× | Claude (final review) |
| D18 | Lifecycle deletes versions after their lock ends | Yes in the baseline; §5 shows the bill if it never does | AD-7 build gate |
| D12 | Secrets | 5 (capture App, restore App, vault GitHub identity, webhook secret, link-signing key) | AD-10, D-C |
| D13 | CloudWatch alarms | 11, including the watchdog's own monitor | AD-21 |
| D14 | Cost Explorer API calls | 62 a month | Claude |
| D15 | Container images | 2 GB | Claude |
| D16 | Logs ingested | 0.5 GB a month (5 GB at 10×) | Claude |

### 3.3 How the active set drives storage

- An active repository changes every day, so it writes a new base every 8 days: about 3.8 bases a month per active repo.
- A retired chain stays locked 365 more days, so each active repo holds about 47 bases at steady state.
- Dormant repositories keep their first base only.
- The resulting Deep Archive volume is about 60 GB today and 600 GB at 10×, which is still under $0.75 a month.

## 4. Prices used (eu-west-1)

| Service | Price | Verified |
|---|---|---|
| S3 Standard | $0.023/GB-month; PUT $0.005 per 1,000; GET $0.0004 per 1,000 | Yes |
| S3 Glacier Deep Archive | $0.00099/GB-month; PUT and lifecycle transition $0.055 per 1,000; 40 KB overhead per object; 180-day minimum | Yes |
| Deep Archive Standard retrieval | $0.02/GB + $0.11 per 1,000 requests; up to 12 h | Yes |
| Lambda arm64 | $0.0000133334 per GB-second; $0.20 per million requests | Yes |
| Fargate ARM64 | $0.03238 per vCPU-hour; $0.00356 per GB-hour | Yes |
| EC2 t4g.small / t4g.medium | $0.0184 / $0.0368 per hour | Yes |
| EBS gp3 | $0.088/GB-month | **Unverified** for eu-west-1 |
| Public IPv4 | $0.005 per hour | Yes |
| Step Functions Standard | $0.000025 per state transition | Yes |
| SQS FIFO | $0.50 per million requests | Yes |
| DynamoDB on-demand | $0.705 per million writes; $0.1415 per million reads; $0.283/GB; point-in-time recovery $0.22/GB | Yes |
| Secrets Manager | $0.40 per secret-month; $0.05 per 10,000 calls | Yes |
| CloudTrail data events | $0.10 per 100,000 (logs stored in S3 Standard) | Yes |
| EventBridge custom events | $1.00 per million | Yes (cross-account price **unverified**) |
| CloudWatch Logs / alarms | $0.57/GB ingested, $0.03/GB stored; $0.10 per alarm-month | Yes |
| SES | $0.10 per 1,000 emails out; $0.10 per 1,000 in | Yes |
| ECR | $0.10/GB-month | Yes |
| Cost Explorer API | $0.01 per request | Yes |
| Data transfer out to internet | $0.09/GB (in: free) | Yes |
| GitHub LFS download bandwidth | $0.0875/GB | **Unverified** |

## 5. Design B′, line by line

<!-- BEGIN:breakdown -->
| Line | Today m1 | Today m12 | Today m36 | 10× m1 | 10× m12 | 10× m36 |
|---|---|---|---|---|---|---|
| Vault: bases in Deep Archive | $0.02 | $0.07 | $0.07 | $0.18 | $0.68 | $0.74 |
| Vault: largest repository's bases | $0.01 | $0.05 | $0.05 | $0.01 | $0.05 | $0.05 |
| Vault: additions in Standard | $0.04 | $0.11 | $0.11 | $0.37 | $1.10 | $1.12 |
| Vault: LFS (scenario line) | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 |
| GitHub LFS download bandwidth (scenario line) | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 |
| Vault: records and audit trail | $0.18 | $0.20 | $0.22 | $1.82 | $1.95 | $2.23 |
| Worker: working-copy cache | $0.32 | $0.32 | $0.32 | $3.23 | $3.23 | $3.23 |
| Compute: Lambda | $3.60 | $3.60 | $3.60 | $35.00 | $35.00 | $35.00 |
| Compute: Fargate (batch job / oversized repos) | $0.21 | $0.21 | $0.21 | $0.83 | $0.83 | $0.83 |
| Step Functions | $0.16 | $0.16 | $0.16 | $0.17 | $0.17 | $0.17 |
| SQS FIFO | $0.01 | $0.01 | $0.01 | $0.12 | $0.12 | $0.12 |
| DynamoDB (two tables, PITR) | $0.08 | $0.08 | $0.08 | $0.37 | $0.37 | $0.37 |
| Vault keeper lock requests | $0.01 | $0.01 | $0.01 | $0.05 | $0.05 | $0.05 |
| CloudTrail data events + EventBridge | $0.11 | $0.14 | $0.14 | $1.04 | $1.40 | $1.40 |
| Secrets Manager | $2.10 | $2.10 | $2.10 | $2.10 | $2.10 | $2.10 |
| CloudWatch logs and alarms | $1.40 | $1.56 | $1.56 | $4.10 | $5.75 | $5.75 |
| SES email | $0.06 | $0.06 | $0.06 | $0.61 | $0.61 | $0.61 |
| ECR images | $0.20 | $0.20 | $0.20 | $0.20 | $0.20 | $0.20 |
| Cost Explorer API (reports) | $0.62 | $0.62 | $0.62 | $0.62 | $0.62 | $0.62 |
| Restores and restore tests | $0.04 | $0.04 | $0.04 | $0.04 | $0.04 | $0.04 |
| **Total** | **$9.17** | **$9.55** | **$9.58** | **$50.86** | **$54.27** | **$54.64** |
<!-- END:breakdown -->

Month 1, month 12 and steady state (month 36) differ only slightly. Routine data levels off after a year **only if the AD-7 lifecycle build gate passes** (lifecycle deletes versions once their locks end). The last two columns show the bill if it never does and no fallback is in place. At-risk data keeps growing while nobody decides, but it's so small that the bill barely moves:

<!-- BEGIN:growth -->
| Month | Today: total | Today: Deep Archive line | 10×: total | Today if lifecycle never deletes | 10× if lifecycle never deletes |
|---|---|---|---|---|---|
| 12 | $9.55 | $0.07 | $54.27 | $9.55 | $54.27 |
| 36 | $9.58 | $0.07 | $54.64 | $9.93 | $57.34 |
| 60 | $9.59 | $0.08 | $54.68 | $10.29 | $60.12 |
| 120 | $9.60 | $0.09 | $54.79 | $11.19 | $67.07 |
<!-- END:growth -->

## 6. Quiet days (PRD COST-5)

<!-- BEGIN:quiet -->
| Quiet day (no pushes) | Today | At 10× |
|---|---|---|
| New backup data | 0 bytes | 0 bytes |
| New records and audit entries | 372 KB | 3720 KB |
| Cost of that day's run (batch job checks, records, data events, watchdog) | $0.01 | $0.04 |
| Monthly bill if every day were quiet (includes fixed costs) | $5.59 | $14.70 |
<!-- END:quiet -->

A quiet day adds **no backup data**. Its run costs about a cent: a short batch job that checks each repository, plus records and audit events. The rest of a quiet month's bill is fixed: secrets, alarms, cost reports and logs.

## 7. Which assumption moves the bill most, and what if it's wrong

**Capture compute: pushes per day × seconds per capture.** Compute is about 40% of today's bill and 66% of the bill at 10×.

<!-- BEGIN:sensitivity -->
| Case (design B′, month 36) | Today | At 10× |
|---|---|---|
| Baseline | $9.58 | $54.64 |
| Pushes 100 a day | $7.59 | $34.67 |
| **Pushes 400 a day** | $13.58 | $94.57 |
| Capture 10 s | $7.93 | $38.13 |
| **Capture 40 s** | $12.88 | $87.65 |
| Rewrites 20 a week | $9.70 | $55.78 |
| Emails 200 a day | $10.14 | $60.25 |
| Cache old versions kept 7 days (before the change) | $10.77 | $66.51 |
| **LFS scenario** (3 × 5 GB files changed weekly) | $16.22 | $61.28 |
| Routine retention 180 days instead of 365 | $9.49 | $53.94 |
| Largest repository dormant (not modeled as active) | $9.53 | $54.58 |
<!-- END:sensitivity -->

**Capture duration also decides B′ versus D at 10×:**

<!-- BEGIN:a_vs_d -->
| Capture duration | B′ at 10× | D at 10× | Cheaper at 10× |
|---|---|---|---|
| 10 s | $38.13 | $57.94 | B′ by $19.81 |
| 20 s | $54.64 | $57.94 | B′ by $3.31 |
| 25 s | $62.89 | $57.94 | D by $4.95 |
| 40 s | $87.65 | $57.94 | D by $29.71 |
<!-- END:a_vs_d -->

- **If pushes double (400 a day),** today's bill rises by about $4. At 10× it reaches about $95 a month, still within the 10× rule relative to the same push rate today.
- **If captures take 40 s,** the 10× bill rises to about $88, and the VM would be cheaper at that scale (break-even about 22 s). Capture duration is measured in the build, and the VM decision is revisited with the real figure.
- **Routine retention of 180 days instead of 365** saves about **$0.09 a month today and $0.70 at 10×** (a row in the table above), which is why the 1-year retention was kept.
- **LFS** adds about **$6.60 a month** in the scenario. Almost all of it is GitHub's LFS download charge (price unverified), not AWS storage.
- **Rewrite events and emails barely move the bill.** Their real cost is alert noise, which PRD SM-10 watches.

## 8. What isn't modeled

- **Free tiers:** excluded on purpose, so the comparison is honest. Lambda's free tier alone could cover most of today's compute.
- **Taxes, support plans, and the management account's own costs.**
- **Engineering and operations time.** It's not an AWS cost, but it's the reason the product owner chose B′ over full B.
- **GitHub plan costs:** git clones by a GitHub App are assumed free (**unverified**).
- **VM extras for design D:** EBS snapshots and a second VM for availability. Either would raise D's cost.
- **Additions over 128 KB:** treated as absent, since the average push is 50 KB. Any that occur stay in Standard until the notary tags them as verified (normally under a day), then move to Deep Archive, at negligible cost.
- **The keeper-expire fallback** (if the lifecycle gate fails): its requests aren't modeled; §5 shows the growth it would prevent.
