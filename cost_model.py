"""Strata cost model (eu-west-1 list prices, no free tier). Chosen design: B′ (design_b_prime).

Every number the bill depends on is an explicit assumption below.
Run:  python3 cost_model.py   -> prints markdown tables used in COST-MODEL.md
"""
from dataclasses import dataclass, replace

GB = 1.0
MB = 1 / 1024
KB = 1 / (1024 * 1024)
DAYS_PER_MONTH = 30.4
HOURS_PER_MONTH = 730

# ---------------------------------------------------------------- prices (eu-west-1)
# Sources: research-aws-github.md and research-prices-euw1.md (AWS Price List API, Sept 2026).
P = dict(
    s3_std_gb=0.023, s3_std_put=0.005 / 1000, s3_std_get=0.0004 / 1000,
    da_gb=0.00099, da_put=0.055 / 1000,
    da_overhead_std_gb=8 * KB, da_overhead_da_gb=32 * KB,       # per archived object
    da_restore_gb=0.02, da_restore_req=0.11 / 1000,
    lambda_gbs=0.0000133334, lambda_req=0.20 / 1e6, lambda_tmp_gbs=0.0000000340,
    fargate_vcpu_h=0.03238, fargate_gb_h=0.00356,
    sfn_transition=0.000025,
    sqs_fifo_req=0.50 / 1e6,
    ddb_write=0.705 / 1e6, ddb_read=0.1415 / 1e6, ddb_gb=0.283, ddb_pitr_gb=0.22,
    secret_month=0.40, secret_call=0.05 / 10000,
    cloudtrail_data_event=0.10 / 100000,
    eventbridge_event=1.00 / 1e6,
    logs_ingest_gb=0.57, logs_store_gb=0.03, alarm=0.10,
    ses_out=0.10 / 1000, ses_in=0.10 / 1000,
    ecr_gb=0.10, cost_explorer_req=0.01,
    egress_gb=0.09, ipv4_h=0.005,
    t4g_small_h=0.0184, t4g_medium_h=0.0368,
    ebs_gp3_gb=0.088,                     # UNVERIFIED for eu-west-1
    github_lfs_gb=0.0875,                 # UNVERIFIED (GitHub LFS bandwidth overage)
)


@dataclass
class A:  # assumptions
    repos: int = 93
    git_gb: float = 4.0                    # total Git data (Orvex contact)
    active_share: float = 0.30             # share of repos that change on a given day (treated as a fixed active set)
    pushes_per_day: float = 200
    push_kb: float = 50                    # new Git data per push
    rewrites_per_week: float = 1
    emails_per_day: float = 20
    restores_per_month: float = 2          # 1 monthly test + 1 real
    restore_gb: float = 0.2                # mid-size repo chain read per restore
    chain_changed_days: int = 7            # AD-2
    routine_retention_days: int = 365
    record_retention_days: int = 1095
    capture_seconds: float = 20            # per capture with new data (download cache, fetch, bundle, upload, claim)
    capture_mem_gb: float = 2.0
    capture_tmp_gb: float = 2.0
    quick_check_seconds: float = 2         # daily-run check of an unchanged repo
    base_build_seconds: float = 30
    cache_noncurrent_days: int = 1         # housekeeping lifecycle on the worker cache (user decision: 1 day)
    record_kb_per_capture: float = 5       # repo-state + capture records
    run_record_kb_per_repo: float = 2
    audit_entries_per_capture: float = 3
    audit_kb: float = 1
    lfs_gb_changed_per_month: float = 0.0  # LFS scenario: 3 x 5 GB weekly = 3*5*4.35
    secrets: int = 5                       # capture key, restore key, vault GitHub identity key (D-C), webhook secret, link-signing key
    alarms: int = 11                       # incl. the watchdog's own monitor alarm (AD-21)
    daily_records_per_repo: float = 2      # capture record + audit entry per repo per daily run, even when unchanged
    notary_seconds_per_mb: float = 0.05    # notary read + verify time per MB of base/large object
    keeper_requests_per_retired_chain: float = 10  # hold releases on a retired chain (base + additions)
    deleted_repos_per_year: float = 2      # deleted repositories (all content at-risk)
    batch_parallelism: int = 4             # design B/B': captures run in parallel inside the batch job
    watchdog_runs_per_day: int = 96        # every 15 minutes (AD-13)
    largest_repo_gb: float = 1.0           # W9: modeled as its own active repository, on top of the active set (conservative)
    vm_cores: int = 2                      # design D: vCPUs per t4g instance
    vm_utilisation: float = 0.5            # design D: target utilization, leaving headroom for FR-18's 15-minute start
    lifecycle_deletes: bool = True         # AD-7 build gate: lifecycle deletes versions after their lock ends
    cost_explorer_calls_per_month: float = 2 * 31   # daily email + monthly email, two accounts
    ecr_gb: float = 2.0                    # capture image (worker) + notary image (vault)
    logs_gb_per_month: float = 0.5


def months_retained(days):
    return days / DAYS_PER_MONTH


def design_a(a: A, month: int):
    """Chosen design: Step Functions + Lambda (+Fargate when needed), S3 cache, vault, notary, keeper."""
    c = {}
    active = a.repos * a.active_share
    active_repo_gb = a.git_gb * a.active_share / active
    dormant_gb = a.git_gb * (1 - a.active_share)

    # -- bases (Deep Archive): active repos write a new base every (chain_changed_days + 1) changed days
    bases_per_month_active = active * DAYS_PER_MONTH / (a.chain_changed_days + 1)
    base_gb_per_month = bases_per_month_active * active_repo_gb
    chain_life_m = months_retained(a.chain_changed_days + 1)
    keep_m = months_retained(a.routine_retention_days) + chain_life_m
    if not a.lifecycle_deletes:          # gate fails and no fallback: routine data is never deleted
        keep_m = 10 ** 6
    held_months = min(month, keep_m)
    base_gb = a.git_gb + base_gb_per_month * held_months if month >= 1 else a.git_gb
    base_objects = a.repos + bases_per_month_active * held_months

    # -- rewrites: dependency set kept 3 years instead of ~1 year (extra retention on one chain per event)
    # at-risk data is kept 3 years, then auto-extended while nobody decides (AD-7): no cap
    rewrite_extra_months = max(0, month - keep_m)
    rewrites_per_month = a.rewrites_per_week * 4.35
    deleted_gb_per_month = a.deleted_repos_per_year / 12 * (a.git_gb / a.repos)
    at_risk_gb = (rewrites_per_month * active_repo_gb + deleted_gb_per_month) * rewrite_extra_months

    # -- additions (mostly < 128 KB -> S3 Standard)
    adds_per_month = a.pushes_per_day * DAYS_PER_MONTH
    add_gb = adds_per_month * a.push_kb * KB * min(month, keep_m)

    # -- LFS (Deep Archive, whole files)
    lfs_gb = a.lfs_gb_changed_per_month * min(month, keep_m)

    c["Vault: bases in Deep Archive"] = (base_gb + at_risk_gb) * P["da_gb"] \
        + base_objects * (P["da_overhead_std_gb"] * P["s3_std_gb"] + P["da_overhead_da_gb"] * P["da_gb"]) \
        + bases_per_month_active * (P["s3_std_put"] + P["da_put"]) \
        + base_gb_per_month * (1 / DAYS_PER_MONTH) * P["s3_std_gb"]   # AD-3: bases sit 1 day in Standard for notary verification, then transition (transition priced as a Deep Archive PUT)
    # -- the largest repository (W9) as its own active line: a 1 GB base every 8 days, staged and verified, then Deep Archive
    big_bases_per_month = DAYS_PER_MONTH / (a.chain_changed_days + 1)
    big_gb = a.largest_repo_gb * big_bases_per_month * min(month, keep_m)
    c["Vault: largest repository's bases"] = big_gb * P["da_gb"] + big_bases_per_month * (P["s3_std_put"] + P["da_put"]) \
        + a.largest_repo_gb * big_bases_per_month / DAYS_PER_MONTH * P["s3_std_gb"] \
        + a.largest_repo_gb * 1024 * big_bases_per_month * a.notary_seconds_per_mb * 2.0 * P["lambda_gbs"]
    c["Vault: additions in Standard"] = add_gb * P["s3_std_gb"] + adds_per_month * P["s3_std_put"]
    c["Vault: LFS (scenario line)"] = lfs_gb * P["da_gb"] + (a.lfs_gb_changed_per_month / 5) * (P["s3_std_put"] + P["da_put"]) \
        + a.lfs_gb_changed_per_month * (1 / DAYS_PER_MONTH) * P["s3_std_gb"]   # D-D: staged 1 day in Standard for verification
    c["GitHub LFS download bandwidth (scenario line)"] = a.lfs_gb_changed_per_month * P["github_lfs_gb"]

    # -- records and audit (Standard, 3 years)
    captures_per_month = adds_per_month
    rec_gb_month = (captures_per_month * (a.record_kb_per_capture + a.audit_entries_per_capture * a.audit_kb)
                    + a.repos * a.run_record_kb_per_repo * DAYS_PER_MONTH) * KB
    rec_puts = captures_per_month * (2 + a.audit_entries_per_capture) + a.repos * DAYS_PER_MONTH * a.daily_records_per_repo + DAYS_PER_MONTH * 10
    c["Vault: records and audit trail"] = rec_gb_month * min(month, months_retained(a.record_retention_days)) * P["s3_std_gb"] \
        + rec_puts * P["s3_std_put"]

    # -- worker cache: current copies + noncurrent versions kept cache_noncurrent_days
    cache_gb = a.git_gb + a.pushes_per_day * active_repo_gb * a.cache_noncurrent_days
    c["Worker: working-copy cache"] = cache_gb * P["s3_std_gb"] + adds_per_month * (P["s3_std_put"] + P["s3_std_get"])

    # -- compute
    capture_gbs = adds_per_month * a.capture_seconds * a.capture_mem_gb
    quick_gbs = a.repos * DAYS_PER_MONTH * a.quick_check_seconds * a.capture_mem_gb
    base_gbs = bases_per_month_active * a.base_build_seconds * a.capture_mem_gb
    tmp_gbs = (adds_per_month * a.capture_seconds) * max(0, a.capture_tmp_gb - 0.5)
    other_gbs = (adds_per_month * 3 + a.repos * DAYS_PER_MONTH * 1) * 0.5   # receiver, notary claims, keeper, mailer, sweep
    notary_gbs = (base_gb_per_month + a.lfs_gb_changed_per_month) * 1024 * a.notary_seconds_per_mb * 2.0   # read + verify bases and large objects (D-D)
    vault_gbs = (a.watchdog_runs_per_day + 96) * DAYS_PER_MONTH * 3 * 0.5   # watchdog every 15 min + vault escalation sweep
    invocations = adds_per_month * 5 + a.repos * DAYS_PER_MONTH * 3
    c["Compute: Lambda"] = (capture_gbs + quick_gbs + base_gbs + other_gbs + notary_gbs + vault_gbs) * P["lambda_gbs"] \
        + tmp_gbs * P["lambda_tmp_gbs"] + invocations * P["lambda_req"]
    c["Compute: Fargate (batch job / oversized repos)"] = 0.0   # largest repo ~1 GB fits Lambda (10 GB disk, 15 min)

    # -- orchestration and queues
    transitions = _daily_run_transitions(a) + rewrites_per_month * 15 + 20 * DAYS_PER_MONTH * 10 \
        + a.restores_per_month * 30
    c["Step Functions"] = transitions * P["sfn_transition"]
    c["SQS FIFO"] = (adds_per_month + a.repos * DAYS_PER_MONTH) * 4 * P["sqs_fifo_req"]
    ddb_writes = (adds_per_month + a.repos * DAYS_PER_MONTH) * 4 + a.emails_per_day * DAYS_PER_MONTH * 3
    c["DynamoDB (two tables, PITR)"] = ddb_writes * P["ddb_write"] + ddb_writes * P["ddb_read"] \
        + 0.1 * (P["ddb_gb"] + P["ddb_pitr_gb"])

    # -- security, monitoring, email
    keeper_requests = bases_per_month_active * a.keeper_requests_per_retired_chain
    c["Vault keeper lock requests"] = keeper_requests * P["s3_std_put"]
    data_events = rec_puts + adds_per_month + bases_per_month_active + keeper_requests + a.repos * DAYS_PER_MONTH * 20 \
        + a.restores_per_month * 100   # vault bucket + restore bucket data events
    trail_gb = data_events * 1.5 * KB * min(month, 12)
    c["CloudTrail data events + EventBridge"] = data_events * P["cloudtrail_data_event"] + 5000 * P["eventbridge_event"] \
        + trail_gb * P["s3_std_gb"]
    c["Secrets Manager"] = a.secrets * P["secret_month"] + 20000 * P["secret_call"]
    c["CloudWatch logs and alarms"] = a.logs_gb_per_month * P["logs_ingest_gb"] \
        + a.logs_gb_per_month * min(month, 12) * P["logs_store_gb"] + a.alarms * P["alarm"]
    c["SES email"] = a.emails_per_day * DAYS_PER_MONTH * P["ses_out"] + 30 * P["ses_in"]
    c["ECR images"] = a.ecr_gb * P["ecr_gb"]
    c["Cost Explorer API (reports)"] = a.cost_explorer_calls_per_month * P["cost_explorer_req"]
    c["Restores and restore tests"] = a.restores_per_month * (a.restore_gb * (P["da_restore_gb"] + P["egress_gb"] / 2)
                                                               + 50 * P["da_restore_req"])
    return c


def _batch_hours(a: A):
    active = a.repos * a.active_share
    return (a.repos * a.quick_check_seconds + active * a.capture_seconds) / a.batch_parallelism / 3600 + 0.1


def _daily_run_transitions(a: A):
    return DAYS_PER_MONTH * (a.repos * 8 + 50)


def _batch_job(c, a: A):
    h = _batch_hours(a)
    c["Compute: Fargate (batch job / oversized repos)"] = DAYS_PER_MONTH * h * (1 * P["fargate_vcpu_h"] + 2 * P["fargate_gb_h"]
                                                                                 + P["ipv4_h"])
    quick_gbs = a.repos * DAYS_PER_MONTH * a.quick_check_seconds * a.capture_mem_gb
    c["Compute: Lambda"] -= quick_gbs * P["lambda_gbs"]
    c["SQS FIFO"] = a.pushes_per_day * DAYS_PER_MONTH * 4 * P["sqs_fifo_req"]   # daily run no longer uses the queue
    return c


def design_b(a: A, month: int):
    """Single scheduled batch job (Fargate) for the daily run; per-push captures still on Lambda (FR-18 / AD-4).
    No Step Functions at all: restore, event-handling and retention flows are hand-built too."""
    c = _batch_job(design_a(a, month), a)
    c["Step Functions"] = 0.0
    return c


def design_b_prime(a: A, month: int):
    """Hybrid B': daily run as one Fargate batch job; Step Functions kept for restore, event and retention flows."""
    c = _batch_job(design_a(a, month), a)
    c["Step Functions"] -= _daily_run_transitions(a) * P["sfn_transition"]
    return c


def design_d(a: A, month: int):
    """Always-on Graviton VM(s) do all captures with caches on local disk; vault side unchanged.
    Instance count scales with capture work so FR-18 (15-minute start) and the daily run still fit."""
    import math
    c = design_a(a, month)
    work_s = a.pushes_per_day * a.capture_seconds + a.repos * a.quick_check_seconds
    n = max(1, math.ceil(work_s / (86400 * a.vm_cores * a.vm_utilisation)))
    vm_h = P["t4g_medium_h"] if a.pushes_per_day > 600 else P["t4g_small_h"]
    disk_gb = max(20, a.git_gb * 3)
    c["Compute: Lambda"] = (a.pushes_per_day * DAYS_PER_MONTH * 3 + a.repos * DAYS_PER_MONTH) * 0.5 * P["lambda_gbs"]  # receiver, notary, keeper, mailer
    c["Compute: Fargate (batch job / oversized repos)"] = 0.0
    c["Compute: Graviton VM + disk + public IPv4"] = n * (HOURS_PER_MONTH * (vm_h + P["ipv4_h"]) + disk_gb * P["ebs_gp3_gb"])
    c["Worker: working-copy cache"] = 0.0
    c["Step Functions"] = 0.0
    return c


def quiet_day_cost(a: A):
    """Cost of one quiet day's run (no pushes) in the chosen design B′: batch job, records, data events, watchdog."""
    h = (a.repos * a.quick_check_seconds) / a.batch_parallelism / 3600 + 0.1   # B': daily batch job, nothing to capture
    quick = h * (1 * P["fargate_vcpu_h"] + 2 * P["fargate_gb_h"] + P["ipv4_h"])
    sfn = 0.0
    recs = (a.repos * a.daily_records_per_repo + 10) * P["s3_std_put"]
    events = (a.repos * (a.daily_records_per_repo + 20)) * P["cloudtrail_data_event"]
    vault = (a.watchdog_runs_per_day + 96) * 3 * 0.5 * P["lambda_gbs"]
    new_storage_gb = (a.repos * a.run_record_kb_per_repo + a.repos * a.daily_records_per_repo * a.audit_kb) * KB
    return quick + sfn + recs + events + vault, new_storage_gb


def total(c):
    return sum(c.values())


def scale10(a: A):
    return replace(a, repos=a.repos * 10, git_gb=a.git_gb * 10, pushes_per_day=a.pushes_per_day * 10,
                   rewrites_per_week=a.rewrites_per_week * 10, emails_per_day=a.emails_per_day * 10,
                   logs_gb_per_month=a.logs_gb_per_month * 10)


def fmt(x):
    return f"${x:,.2f}"


def tables():
    base = A()
    lfs = replace(base, lfs_gb_changed_per_month=3 * 5 * 4.35)
    out = {}

    rows = {}
    for scen, a in (("t", base), ("x", scale10(base))):
        for m in (1, 12, 36):
            for k, v in design_b_prime(a, m).items():
                rows.setdefault(k, {})[(scen, m)] = v
    t = ["| Line | Today m1 | Today m12 | Today m36 | 10× m1 | 10× m12 | 10× m36 |", "|---|---|---|---|---|---|---|"]
    for k, r in rows.items():
        t.append(f"| {k} | " + " | ".join(fmt(r[(s_, m)]) for s_ in "tx" for m in (1, 12, 36)) + " |")
    t.append("| **Total** | " + " | ".join(f"**{fmt(total(design_b_prime(a, m)))}**" for a in (base, scale10(base)) for m in (1, 12, 36)) + " |")
    out["breakdown"] = "\n".join(t)

    t = ["| Design | Today | At 10× | 10× bill ÷ today's | Today vs B′ |", "|---|---|---|---|---|"]
    bp = total(design_b_prime(base, 36))
    for name, f in (("**B′. Hybrid: daily batch job + Step Functions for restore and events (chosen)**", design_b_prime), ("A. Orchestrated pipeline (Step Functions for everything)", design_a),
                    ("B. Batch job, no Step Functions at all", design_b), ("D. Always-on Graviton VM", design_d)):
        tt, xx = total(f(base, 36)), total(f(scale10(base), 36))
        t.append(f"| {name} | {fmt(tt)} | {fmt(xx)} | {xx/tt:.1f}× | {tt/bp:.2f}× |")
    out["designs"] = "\n".join(t)

    t = ["| Case (design B′, month 36) | Today | At 10× |", "|---|---|---|"]
    cases = [
        ("Baseline", base),
        ("Pushes 100 a day", replace(base, pushes_per_day=100)),
        ("**Pushes 400 a day**", replace(base, pushes_per_day=400)),
        ("Capture 10 s", replace(base, capture_seconds=10)),
        ("**Capture 40 s**", replace(base, capture_seconds=40)),
        ("Rewrites 20 a week", replace(base, rewrites_per_week=20)),
        ("Emails 200 a day", replace(base, emails_per_day=200)),
        ("Cache old versions kept 7 days (before the change)", replace(base, cache_noncurrent_days=7)),
        ("**LFS scenario** (3 × 5 GB files changed weekly)", lfs),
        ("Routine retention 180 days instead of 365", replace(base, routine_retention_days=180)),
        ("Largest repository dormant (not modeled as active)", replace(base, largest_repo_gb=0.0)),
    ]
    for name, a in cases:
        t.append(f"| {name} | {fmt(total(design_b_prime(a, 36)))} | {fmt(total(design_b_prime(scale10(a), 36)))} |")
    out["sensitivity"] = "\n".join(t)

    t = ["| Capture duration | B′ at 10× | D at 10× | Cheaper at 10× |", "|---|---|---|---|"]
    for sec in (10, 20, 25, 40):
        a = replace(base, capture_seconds=sec)
        av, dv = total(design_b_prime(scale10(a), 36)), total(design_d(scale10(a), 36))
        t.append(f"| {sec} s | {fmt(av)} | {fmt(dv)} | {'B′' if av < dv else 'D'} by {fmt(abs(av - dv))} |")
    out["a_vs_d"] = "\n".join(t)

    qt, qs = quiet_day_cost(base)
    qx, qxs = quiet_day_cost(scale10(base))
    out["quiet"] = "\n".join([
        "| Quiet day (no pushes) | Today | At 10× |", "|---|---|---|",
        f"| New backup data | 0 bytes | 0 bytes |",
        f"| New records and audit entries | {qs*1024*1024:.0f} KB | {qxs*1024*1024:.0f} KB |",
        f"| Cost of that day's run (batch job checks, records, data events, watchdog) | {fmt(qt)} | {fmt(qx)} |",
        f"| Monthly bill if every day were quiet (includes fixed costs) | {fmt(total(design_b_prime(replace(base, pushes_per_day=0), 36)))} | {fmt(total(design_b_prime(scale10(replace(base, pushes_per_day=0)), 36)))} |",
    ])

    nl = replace(base, lifecycle_deletes=False)
    t = ["| Month | Today: total | Today: Deep Archive line | 10×: total | Today if lifecycle never deletes | 10× if lifecycle never deletes |", "|---|---|---|---|---|---|"]
    for m in (12, 36, 60, 120):
        t.append(f"| {m} | {fmt(total(design_b_prime(base, m)))} | {fmt(design_b_prime(base, m)['Vault: bases in Deep Archive'])} | {fmt(total(design_b_prime(scale10(base), m)))} | {fmt(total(design_b_prime(nl, m)))} | {fmt(total(design_b_prime(scale10(nl), m)))} |")
    out["growth"] = "\n".join(t)
    return out


def update_doc(path="COST-MODEL.md"):
    import re
    doc = open(path).read()
    for key, table in tables().items():
        doc, n = re.subn(rf"(<!-- BEGIN:{key} -->\n).*?(<!-- END:{key} -->)", lambda m: m.group(1) + table + "\n" + m.group(2), doc, flags=re.S)
        if n != 1:
            raise SystemExit(f"marker {key} missing in {path}")
    open(path, "w").write(doc)


if __name__ == "__main__":
    import sys
    tb = tables()
    with open("results.md", "w") as f:
        for k, v in tb.items():
            f.write(f"## {k}\n\n{v}\n\n")
    if "--update-doc" in sys.argv:
        update_doc()
    print(open("results.md").read())
