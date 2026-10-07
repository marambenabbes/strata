# AI_LOG

How I used Claude and BMAD on Strata, every decision I made in the brief, PRD and architecture sessions (including the Challenge review and the final review), and the times I overruled Claude. Every entry comes from a decision log (`.memlog.md`) or from the session itself:

- Brief log: `_bmad-output/planning-artifacts/briefs/brief-repo-backup-service-2026-09-29/.memlog.md`
- PRD log: `_bmad-output/planning-artifacts/prds/prd-repo-backup-service-2026-10-04/.memlog.md`
- Architecture log: `_bmad-output/planning-artifacts/architecture/architecture-repo-backup-service-2026-10-05/.memlog.md`

These decision logs are kept in my working repository and are not published here; the evidence lines below name the log entry each item comes from.

## Five headline overrules

The assignment asks for three to five times I overruled Claude. These are the five I consider most important; all 20, with evidence, are in [Times I overruled Claude](#times-i-overruled-claude).

1. **Unanswered expiry warnings (brief).** Claude read "an unanswered warning keeps the data" as another full 3 years of retention. I chose to extend only by the Glacier minimum storage period (90 or 180 days), so Orvex never pays for unused minimum storage. (Full list #1.)
2. **Escalation must end with a decision-maker (PRD).** Claude proposed that an org owner only chases an unresponsive budget owner. I required that every escalation chain ends with someone who can decide: an org owner may decide, but never on their own request. (#8.)
3. **Every repository must be backed up (PRD).** Claude proposed that a run fails only if more than 10% of repositories fail. I required 100%: any failed repository makes the run fail and triggers the automatic re-run. (#11.)
4. **Chain limit (architecture).** Claude proposed starting a new full base after 30 days with changes. I chose 7, for a shorter restore chain, faster recovery and less dependence on old objects. (#13.)
5. **The daily run's design (architecture).** After rechecking, Claude recommended keeping Step Functions for everything (design A). I chose the hybrid B′: the daily backup runs as one batch job, while Step Functions stays for restore and event handling. This keeps the architecture simpler and avoids adding custom orchestration (as the full batch design would) just to save a very small amount. (#19.)

## How I used Claude and BMAD

I used Claude Code with Claude Opus, structured by BMAD v6.12 skills, following the assignment's steps.

| Step | BMAD skill | Dates | What I used Claude for |
|---|---|---|---|
| Set up | `npx bmad-method install` | 2026-09-23 | Installing BMAD into this repository |
| Frame | `bmad-product-brief` | 2026-09-29 to 2026-10-04 (final) | Facilitating the brief one question at a time, drafting the text, reviewing and polishing it |
| Specify | `bmad-prd` | 2026-10-04 to 2026-10-05 (final) | Turning the final brief and the assignment into a detailed PRD for the engineers |
| Design | `bmad-architecture` | 2026-10-05 to 2026-10-07 | Working through the architecture decisions with me (coaching path); then the architecture document, cost model, restore runbook and README |
| Challenge | `bmad-review` (adversarial lens, then all five lenses) | 2026-10-07 | The adversarial Challenge review of the architecture, cost model and runbook; then a final five-lens review of all deliverables. I decided every fix |

**Brief.**
- Claude facilitated the brief and drafted the text. I made the decisions on scope, roles, retention, locks and escalation.
- After the Orvex contact's answers arrived (2026-10-03), I updated the brief with them and finalized it again.

**PRD.**
- I told Claude the brief's decisions were final and must not be changed. Midway through, I made the assignment PDF a source of truth.
- Claude extracted the brief, its addendum and its decision log, and researched existing GitHub-backup tools.
- Claude listed every gap the brief left open, each with a proposed default. I accepted, changed or rejected each one before Claude drafted the PRD.

**Architecture.**
- I chose the coaching path: Claude laid out the options for each decision, and I made the decision.
- Claude researched AWS and GitHub behavior and checked key claims against their documentation before I relied on them.
- Claude wrote the architecture spine, the architecture document, the cost model script and document, the restore runbook and the README from my decisions.
- Two reviews attacked the result: the adversarial Challenge review and a final review with five lenses. I decided every fix.

**Checking Claude's work.**
- **Checks against my inputs found two places where Claude's draft broke the brief.** It let at-risk data expire without a decision, and it softened the brief's statement that existing products already meet the requirements. Both were corrected.
- **A quality-checklist review and an adversarial review attacked the draft.** The adversarial review found four critical gaps. I decided each fix myself, and rejected or narrowed several of Claude's proposed fixes.
- Vendor prices from Claude's research are marked as needing a re-check; I did not treat them as facts.

## My decisions in the brief session

I chose the coaching path for the brief, one question at a time. Each item below is recorded in the brief log, attributed to me. Where I later changed a decision, only the final version is listed and the change is noted.

**Problem framing**
- Engineers, who lose their code, and the company are the first people affected by a loss.
- Laptop clones are not a backup:
  - each holds only what its owner fetched
  - laptops get lost or damaged
  - after a force-push or branch deletion, the old state may exist on no machine
  - nobody can prove which laptop holds which repository from which date, so recovery must not depend on coincidence
- No claim that Strata beats existing products: Rewind and GitProtect already meet the requirements. Orvex builds for control (its own backups, security, retention rules and cost) and for independence from GitHub.
- Building means owning the AWS bill, rate limits, security, alerting and restore testing.
- I accepted a correction: GitHub does offer branch protection and a 90-day deleted-repo restore. Strata's value is recovery when GitHub access is lost or stolen.
- The vision includes a "Beyond v1" section listing what v1 leaves out (issues and PRs, releases).

**Scope**
- **In v1:** Git data (commits, branches, tags), LFS with no size or file-type limit, and wikis, because they hold important project information.
- **Out of v1:** releases, issues and pull requests, because they add complexity and storage.
- **LFS after the Orvex contact's answers:** Orvex uses none today, but it stays in scope so Strata backs it up automatically when it appears. This replaced my earlier reason that Orvex keeps models and datasets in LFS.
- **LFS volume:** I did not assume I would get GitHub org access; the Orvex contact provides the numbers.
- **Accepted risk:** if a repository is deleted, its issue and PR discussions are lost; code and history come first.

**Roles and security**
- **Three roles, split by knowledge:**
  - the **backup operator**, a technical person such as a DevOps engineer, holds AWS and GitHub access, keeps Strata running, investigates failures, retries, restores and reports
  - the **repo owner** knows the code's importance, investigates force-pushes and deleted branches, and requests extensions
  - the **budget owner** knows the finances and approves or denies extensions
- **Who investigates force-pushes:** I first gave this to the backup operator, then changed it to the repo owner.
- **Extension flow:** the repo owner requests, the budget owner approves, the backup operator carries it out. The operator needs approval to act.
- **Separation of duties:** the backup operator can add backups but cannot delete, modify or weaken their protection. Powers are split so that security and traceability improve, and every operation is transparent.
- **No fourth role:** the second failure contact is another backup operator or an on-call person.
- **Repo owner:** the GitHub team assigned to the repository. I rejected `CODEOWNERS` (it defines review scope, not responsibility) and a hand-kept list (it can't be proven to stay in step with new repositories).
- **No team assigned:** alerts go to all the repository's admins, and the repository is listed in the daily email so the gap is visible before an incident.

**Retention and protection**
- **Two classes:**
  - routine snapshots, whose content still exists in newer backups, kept 1 year and expiring automatically with no approval
  - at-risk data that exists in no newer backup, kept 3 years and needing a decision before it goes
- **Why those periods:** 1 year covers bugs found long after they were introduced and is above the Glacier minimum storage period, so nothing is billed after deletion. 3 years because investigations take long and at-risk data is gone for good once it expires.
- **Cost awareness:** I considered 10× growth and avoided periods that delete data before the Glacier minimum storage period, which would still be billed.
- **Locks:** each lock lasts exactly as long as the retention, so an attacker cannot touch data at any point. Every extension, approved or unanswered, extends the lock by the same period.
- **Expiry warnings:** the repo owner is warned before at-risk data expires and may request an extension. Extending is allowed because it cannot delete or modify backups.
- **Unanswered warnings:** the data is not expired. The warning escalates to someone who can decide, and the extra storage kept is reported. This replaced my earlier rule that every backup expires automatically.
- **Extension cost:** an extension can raise cost, but only through an explicit decision.

**Alerting and escalation**
- Every failure must be loud, including unanswered warnings.
- Failure alerts must always reach someone who can act, so a second contact receives them.
- **Email routing:** the backup operator gets the full daily email; repo owners get alerts only when their repositories are affected; the budget owner gets a monthly cost email and extension requests.
- **Acknowledgment deadlines:**
  - **1 hour** for force-push and branch-deletion alerts, because a live or deployed repository may be affected even though the backup is safe
  - **1 hour** for backup failures, because each failure is a protection gap
  - **24 hours** for repositories without an owner and for retention requests
- **Escalation chain:** assigned team → repo admins → org owner. I first ended the chain with the backup operator, then removed them, because a chain must end with someone who has authority to decide.

**Success criteria and cost**
- **Coverage:** every repository, with all branches and tags, backed up within 24 hours of creation.
- **Restores:** exactly the branches, tags and commit IDs GitHub had on the chosen date, within 24 hours (provisional until storage classes are chosen in the architecture), tested at least monthly.
- **Late runs:** an alert if a run fails or hasn't finished 1 hour after its expected end.
- **Cost:** the monthly bill grows no more than 10× at 10× the data. After the Orvex contact confirmed there is no fixed budget, I replaced the budget ceiling with:
  - comparing at least three credible designs that differ in compute and storage and each meet all requirements, and choosing the cheapest
  - the quiet-day rule, which proves only changes are stored
  - the 10× growth rule, which proves cost scales no worse than linearly
- **Reviews:** I accepted 13 of 14 brief review suggestions and all 4 addendum suggestions. In the final review I applied all 15 suggestions and reworded one myself.

## My decisions in the PRD session

Recorded in the PRD log. I kept the brief's decisions final and used the assignment PDF as the source of truth where it states a requirement.

**Working rules**
- The PRD is for the engineers building Strata, so it must be detailed.
- I chose the fast path: Claude proposed a default for each gap, and I accepted, changed or rejected each one.
- Where my answers conflicted with the brief, Claude flagged the conflict and I resolved it.

**Backup behavior**
- **Schedule:** "daily" only, with no fixed hours.
- **Coverage:** every repository Orvex has. A new repository is captured as soon as its creation event arrives.
- **Quiet day:** zero new backup data, plus a small locked run record that proves the run happened, what it checked and any issue.
- **Retries and rate limits:** automatic retries and rate-limit handling, as the assignment requires. The failure alert goes out once retries are exhausted.
- **Run success:** a run succeeds only if every discovered repository is backed up. If it fails, Strata alerts and re-runs once; a second failure escalates normally.
- **10× growth:** a planning scenario, not a cap, covering 40 GB of Git data plus repositories, branches, tags and daily changes. LFS is modeled separately.
- **Retention clock:** each backed-up day is kept 1 year from that day. Anything it depends on stays as long as needed, automatically and visibly.

**Force-pushes and deletions**
- **Each force-push or deletion is its own event with its own alert,** sent to the affected repo owner.
- I asked Claude to compare two approaches against the assignment, and chose: the daily backup as the guarantee, plus a best-effort capture of overwritten commits as each event arrives, with the result reported. I chose it because the cost is negligible, the complexity moderate, and it adds safety.
- **Tags:** tag moves and deletions are high-risk changes, alerted within 1 hour; the concern is the live repository, since backups stay safe.
- **Routine branch deletions are not incidents** (no 1-hour alert, no 3-year retention), because that would spam alerts. A deletion is routine only if:
  - its commits are still reachable from a branch or tag that still exists, or
  - it was merged into a branch that still exists.
- **Always incidents:**
  - abandoned (unmerged) branches, the safest option
  - more than 5 deletions at once
  - a deletion found only by the daily check, so attackers can't hide deletions as routine
- **Pending confirmation:** a deletion that passes the rules at event time is provisionally routine. The daily run rechecks it; if it isn't confirmed, Strata raises an alert and treats it as an incident. This keeps backups safe without alert spam for normal activity.
- **Floods:** notifications are grouped above 10 events per repository per hour, but every event is still recorded individually.

**Retention decisions**
- **Who decides:** the requester and approver are always different people.
  - The repo owner team requests first; repo admins or an org owner are stand-bys.
  - The budget owner always approves; an org owner stands in only if they didn't make the request.
  - The backup operator never requests or approves; they only carry out.
  - If an extension isn't carried out, the auto-extension keeps the data safe.
- **Org owner** stays the stand-in repo owner, as in the brief.
- **Extension length:** a multiple of the Glacier minimum storage period.
- **Deadlines:** 24 hours is the deadline to acknowledge, not to decide, since evaluating an extension takes longer. The decision deadline is the end of the current lock.
- **Explicit decision required:** at-risk data expires only on an explicit, recorded decision. Otherwise the auto-extension keeps it.
- **Warnings and auto-extension:** the warning comes 30 days before expiry and stays the main warning. The auto-extension is applied 7 days before the lock ends, to leave time to find and fix failures. A failed extension is an alert, and data whose classification fails is treated as at-risk.

**Alerts and access**
- **Email only in v1,** because I don't know whether Orvex has a paging or incident tool; paging is a future option.
- **A missing daily email** is a Strata failure the backup operator must investigate. An email-side outage is an accepted remaining risk.
- **Acknowledgment behavior is specified; the mechanism is left to the architecture.**
- **Alerts follow ownership recorded before the event,** so an attacker can't redirect them.
  - Ownership changes alert the previous owners.
  - Someone who gained a role in the last 7 days can't stop escalation.
- **The backup operator receives only alerts about Strata itself,** not repository alerts.
- **GitHub access belongs to Strata,** not to one person's credentials. Backups are encrypted at rest and in transit.
- **The backup operator can trigger a backup run** but cannot upload or modify backup data directly.

**Restores**
- **No approval needed:** repo owners, repo admins and org owners can start a restore; the backup operator performs restores as part of operations. Only extensions need a request.
- **Scope:** commits, branches, tags, LFS and the wiki.
- **Destination:** always a new private repository in Orvex's GitHub org, never an overwrite.
- **Moving a restored repository outside the org** is a separate human action, and it is reported and alerted.

**Review and finishing**
- I ran both a quality-checklist review and an adversarial review, and decided every critical and high finding.
- I accepted all 12 high findings.
- I accepted every assumption Claude flagged for confirmation, and the additions it proposed:
  - protecting encryption keys
  - flagging unexplained storage growth
  - catching up after missed days


## My decisions in the architecture session

Recorded in the architecture log. For each topic, the final decision comes first. "How it changed" shows earlier versions; they are history, not the current design. Figures marked "(at the time)" come from an earlier cost run.

Design names used below:
- **A:** the orchestrated pipeline (Step Functions runs every capture).
- **B:** a full batch job with no Step Functions.
- **B′:** the hybrid: daily backup as one batch job, Step Functions kept for restore and event handling.
- **D:** an always-on Graviton VM.

**Working rules**
- I chose the coaching path, so that I make the architecture decisions myself with Claude's help.
- The deliverables follow the assignment's list:
  - architecture documents, clear for engineers and coding agents, with diagrams
  - a cost model with every assumption stated
  - a restore runbook for one repository on one date
  - this AI_LOG.md
  - a README that ties them together
- Order: finalize the spine, then the architecture document, cost model, restore runbook and README.
- After the Orvex contact's guidance arrived, I asked Claude to recheck AD-1 to AD-10 against the assignment and their guidance. The results are in AD-3, AD-7 and the retention entry below.
- Environments and the deployment pipeline are left to the build phase, to keep the design simple.

**Design pattern (AD-1)**
- **Final: B′.** The daily backup runs as one scheduled Fargate batch job using the same capture code. The job itself handles retries, parallel captures, rate pacing and the 100% check. One automatic re-run follows a failed run. Step Functions stays for restore, the restore test and event handling. Event captures are unchanged (Lambda, queue and lease).
- **Reason:** it keeps the architecture simpler and avoids adding custom orchestration, as full B would, just to save a very small amount.
- **Rejected:**
  - full B: it would also hand-build restore (including the 12-hour Deep Archive wait), event handling and the restore test, and saves only about $0.15 a month more than B′ (about $0.16 at the time)
  - a fully event-driven design: more complexity, no benefit I could see
- **Final cost:** B′ $9.58 a month today and $54.64 at 10×; A $10.14 and $61.06. B′ saves about $0.55 a month today and $6.40 at 10×.
- **How it changed:**
  - 2026-10-05: I chose A over a single batch job. I followed my PRD's order: meet every requirement, then cheapest, then simplest. The cost difference was small (at the time, about $0.50 a month today and $6 at 10×). The batch job would need hand-built retries, rate-limit handling, failure handling and 100% tracking.
  - When I set my tie-break (below), I kept A again.
  - 2026-10-06: the batch job came out cheaper both today and at 10×, so I asked Claude to recheck it against every requirement. I said I would switch if it could meet everything without too much custom coordination. B′ could meet every requirement and save about $0.60 a month today and $5.60 at 10× (at the time). It needed more custom code and a second orchestration style, so by my tie-break I kept A.
  - 2026-10-07: I asked to switch to full B, with the trade-offs and a requirement check. Claude asked me to confirm first, because B also hand-builds restore, event handling and the restore test. After seeing that, I chose B′.

**Tie-break between designs**
- **Final:** when two designs meet the requirements and the cost difference is small, I prefer the simpler design with less custom code and fewer failure points. It is now in the PRD (COST-1). The architecture applies it per flow: daily run, restore and events.
- **How it changed:** I first used it to keep A. My reason then: the pipeline fits serverless better, because the work is split into short-lived steps with no single large process coordinating everything, and it is simpler and more secure in terms of failures.

**Storage chain (AD-2)**
- **Final:** per repository, one full base backup, then only new objects on days with changes. After 7 days with changes, the next day with changes starts a new full base. This never happens on a quiet day, so the quiet-day rule holds.
- **Reason for 7:** a shorter restore chain, faster recovery and less dependence on old objects.
- **Rejected:**
  - an endless chain: restores and lock management keep growing, and objects get their locks extended without need, which raises cost
  - a monthly full backup: it breaks the quiet-day rule
- **How it changed:** the first limit was 30 additions, about one month if a repository changes once a day. Once Strata captured every push (AD-4), a busy repository could reach 30 additions in one day and write full bases constantly. I changed the limit to 7 days with changes.

**Storage classes (AD-3)**
- **Final:**
  - run records and the audit trail go in S3 Standard
  - backup objects under 128 KB stay in S3 Standard, locked the same way
  - bases and objects of 128 KB or more are written to S3 Standard first. The notary reads and verifies them. A lifecycle rule then moves them to Glacier Deep Archive, but only once they are tagged as verified. The watchdog alerts on objects unverified for more than 24 hours.
- **Why Deep Archive:** it meets the 24-hour restore requirement and is the cheapest option. Fast restores are not a requirement. I rejected Glacier Instant Retrieval (about 4× the cost) and a mix of classes (lifecycle and early-delete charges for no gain at this size).
- **Event captures** follow the same rules. Clear trade-off: commits captured right after an incident can take up to 12 hours to retrieve once in Deep Archive. Keeping event captures in S3 Standard for 30 days is a future option; it is not a requirement, and the current rule is simpler and cheaper.
- **How it changed:**
  - First, all backup data went straight to Deep Archive, event captures included.
  - After the recheck against the Orvex contact's guidance, I added the 128 KB size rule. Per-push captures create many tiny objects, and in Deep Archive their per-file charges would cost more than the data itself, which my PRD rule COST-7 forbids.
  - The first cost run found that the notary could not read bases in Deep Archive. I chose to write new bases to S3 Standard first and move them after one day. I rejected checksum-only verification, because a forged base could then release a real chain.
  - After the Challenge review, I extended this to additions and LFS objects of 128 KB or more, and the move now waits for the verification tag instead of a fixed timer. Nothing is recorded as verified without being read.

**Capturing commits before they can be overwritten (AD-4)**
- **Final:** Strata captures new commits on every push, so they are already stored before a later force-push can overwrite them. GitHub access stays read-only. On a force-push or deletion event, Strata also makes a read-only, best-effort fetch of anything not yet stored, and reports the result. I accepted that best-effort fetch as a residual risk, measured by SM-9.
- After the Challenge review, a fetched "before" commit is stored only if Strata's verified records or GitHub confirm it belongs to that repository. Otherwise the capture reports it as unverifiable.
- **Rejected:** capturing only after a force-push (already too late, and it relies on GitHub still serving the overwritten commits), and giving Strata write access to pin commits (a security problem).

**AWS accounts (AD-5)**
- **Final:** two accounts. A worker account runs the workflows and reads GitHub. A separate vault account holds the backups. Organization policies deny closing or leaving these accounts. The worker can only add files to the vault, never delete or modify them, so a stolen credential cannot directly delete or modify existing backups. The extra IAM complexity is needed to satisfy the tamper-resistance requirement.
- **Residual risk:** the management account's root user can remove those policies or close accounts, so it is protected with hardware MFA held by two people.

**Encryption (AD-6)**
- **Final:** S3-managed encryption (SSE-S3). It's free, there is no key anyone can delete, it still encrypts the backups, and it's simpler. I rejected a customer-managed KMS key, because it is a deletable key to guard.

**Locks and deletion (AD-7)**
- **Locks, final:** S3 Object Lock event holds keep a chain's backups locked while the chain is in use. When a new base retires a chain, the holds are released and each object stays locked one more year. If Strata stops working, the backups stay locked instead of becoming unprotected later. The feature is newer, but the fail-safe behavior matters more here; the fallback is a daily lock extension. After the Challenge review, a default bucket lock of 365 days backs this up.
- **Deletion, final:** S3 lifecycle expiry deletes backups. Claude verified against AWS documentation that a lifecycle rule cannot delete a locked version, so the locks still provide tamper resistance. At-risk data also keeps a legal hold that only a recorded decision removes. Strata holds no delete permission in the vault.
- **Reason:** simpler, cheaper, meets the requirements, and answers the Orvex contact's request to define lifecycle rules.
- **Fallback:** if the lifecycle build gate fails, a pre-defined, narrow expiry role in the vault deletes only versions whose lock has ended, with no legal hold, that the records allow.
- **Housekeeping rules:** incomplete uploads are removed after 1 day; old versions of the worker cache are kept 1 day; restore copies expire after 30 days.
- **How it changed:** I first chose deletion only by Strata's own expiry step, never by a lifecycle rule, because a lifecycle rule cannot check for a recorded decision. After the Orvex contact's guidance I preferred lifecycle expiry, but asked to verify it against the tamper-resistance requirement first. After the verification, I switched. The cache rule was 7 days; I cut it to 1 day (see cost decisions).

**Retention**
- **Final:** I kept the brief's values: 1 year for routine snapshots, 3 years for at-risk data.
- **Reason:** shortening saves very little (at the time: at most about $0.09 a month today and $0.90 at 10×; final cost model: about $0.09 and $0.70), saves nothing below Deep Archive's 180-day minimum, and would shrink the restore and tamper-protection windows.
- **How it changed:** before finalizing, I asked to revisit both values to see whether a shorter policy would still meet the restore and security requirements at lower cost.

**Compute (AD-8)**
- **Final:** event captures run on Lambda (arm64, container image with git). Repositories too big for Lambda run on Fargate (ARM) with the same image. Daily captures run inside the daily batch job (AD-1); oversized repositories are captured on their own within it.
- **Rejected:** Lambda alone (it doesn't work for large repositories) and Fargate alone (more than most captures need, and it costs more). Lambda with a Fargate fallback meets the requirements and is simple, cheap and serverless, while still supporting large repositories.
- The always-on Graviton VM (D) stays in the cost model, so I can compare its cost with my choice.
- **How it changed:** at first, Lambda ran every capture, daily ones included. The daily captures moved into the batch job with B′.

**Working copy and lease (AD-9)**
- **Final:** each repository's working copy is cached in S3 Standard in the worker account. It avoids downloading the whole repository on every capture, which makes incremental capture efficient while staying cheap.
- **Two rules:**
  - the cache is never trusted as a backup: the vault's run record is the only truth, and a missing or mismatched cache is rebuilt
  - only one capture runs per repository at a time, enforced by a per-repository lease in the worker's DynamoDB table. Whichever runtime runs the capture (Lambda, Fargate or the batch job) holds the lease.
- **Rejected:** a full clone on every capture, and a shared file system (EFS), which is very expensive because it needs a network gateway.
- **How it changed:** the lease replaced an earlier hand-off of queue messages to Fargate, which was found unworkable.

**GitHub identities (AD-10, AD-29)**
- **Final: three GitHub Apps.**
  - **Capture App:** read-only, installed on the org. I rejected a machine-user token.
  - **Restore App:** restore-only. I accepted it only on condition that GitHub guarantees it cannot touch existing repositories; otherwise Strata would never write to GitHub and the PRD would change. GitHub documents that an App installed on selected repositories can reach only those and the repositories it creates, but it cannot be installed on zero repositories. One empty placeholder repository is an acceptable trade-off, and the access-change alert covers the remaining risk. Giving the capture App write access was rejected because it breaks the security rule.
  - **Vault App (AD-29):** read-only (members, teams and pull requests), used only by the vault. It resolves repo owners, org owners and emails for retention decisions, so the vault does not trust the worker's claims about ownership. It also lets the notary confirm merged-branch deletions itself, so those are routine (1 year, no alert), as I intended, without trusting the worker.
- **How it changed:** the vault App came from the Challenge review. Pull-request access was added after the cost model rerun.

**Event intake (AD-11)**
- **Final:** GitHub events go through a small receiver into one first-in-first-out queue grouped by repository. The queue now carries event captures only.
- **Reason:** simpler, cheaper, more reliable, fewer components; AWS handles the ordering and retries. I rejected a workflow per event with a lock table.
- **How it changed:** at first the daily run used the same queue. With B′, daily captures run in the batch job.

**Acting on Strata by email (AD-12)**
- **Final:** signed single-use links open a small confirm page with one button. They cover acknowledgments, retention decisions (with a confirmation step) and revocations. Decision links and their confirm page live in the vault. A restore is started by emailing a request to Strata, which checks the sender and replies with a confirm link.
- **Reason:** the simplest option that satisfies the requirements. I rejected email replies and GitHub sign-in.

**Independent watchdog (AD-13)**
- **Final:** the watchdog lives in the vault account and runs at least every 15 minutes. It reads the vault's run records and alerts through the vault's own email sender. It also checks for missing holds, objects left unverified, and versions kept past their lock with no hold, and it sends the "no restore test passed by the 25th" alert. A monitor in the vault alerts if the watchdog itself stops running (AD-21).
- It is independent of the worker account. It can read and alert, but never write or delete backups. I rejected an alarm in the worker account (a shared point of failure) and a third monitoring account.
- **How it changed:** at first it was a daily check. The Challenge review led to the 15-minute schedule and the monitor.

**Region (AD-14)**
- **Final:** eu-west-1 (Ireland). Orvex is UK-based, and I prioritized the lowest cost. It stays configurable in case Orvex has a data-residency requirement.
- **Exception:** one forwarding rule in the management account's us-east-1 sends AWS Organizations events to the vault, because those events are only logged there.

**Build stack (AD-15)**
- **Final:** Python for the application and AWS CDK in Python for the infrastructure: one language for both, with the simplest setup.

**Records (AD-16)**
- **Final:** I accepted Claude's proposal that run records are the single source of truth. They list the exact stored files and versions each backed-up day needs, and they are chained together so tampering shows. My reason: it makes the architecture consistent and gives restores one clear source of truth.
- Since the Challenge review, only the notary writes the records the vault trusts.

**Vault keeper (AD-17)**
- **Final:** every change to locks and holds runs in the vault account, and only after checking the vault's records. The backup operator can trigger an approved extension but has no write rights in the vault.

**Restore (AD-18)**
- **Final:** every restore first builds a private copy in AWS, so a restore still works if GitHub is down. If GitHub is available, the restore App then creates the private GitHub repository. Copies expire after 30 days. The monthly restore test restores into AWS only.
- A requester reaches the AWS copy through a single-use link that issues a 15-minute download link.
- For the manual fallback, I kept a read-only restore role: the backup operator can read the vault and write only to the restore bucket.
- I approved the Challenge review's restore fixes, including CloudTrail on the restore bucket.

**Recipient emails (AD-19)**
- **Final:** alert recipients' email addresses come from GitHub. If GitHub Enterprise Cloud email access isn't available (it needs Enterprise Cloud with a verified domain), Strata falls back to a mapping file of GitHub logins to emails. Since the Challenge review, that file lives in the vault's configuration.

**Operational state (AD-20)**
- **Final:** two DynamoDB tables. The worker table holds alerts, escalation steps, single-use links and leases. The vault table holds decision state. Every change is also written to the vault's audit trail.
- **How it changed:** I first chose one table in the worker account. When decision state moved into the vault (AD-22), I kept it in a second table there instead of putting it back in the worker table. The extra cost is very small, and it keeps the security boundary clear.

**Tamper detection (AD-21)**
- **Final:** I adopted it after the cost model rerun. Claude had added it as a review fix. It includes the watchdog's monitor.

**Notary (AD-22)**
- **Final:** the records the vault keeper trusts are written only by a notary in the vault account. The notary checks the worker's claims against the stored files and reads every object it records as verified. My reason: a lost credential can't lead to lost data.

**Vault deployment (AD-23)**
- **Final:** no automated deployment to the vault. It is deployed only by a person with two-person hardware MFA. My reason: if the GitHub path is compromised, it must not be possible to change the vault keeper or its permissions.

**Live-event path (AD-24)**
- **Final:** one workflow owns live-event handling (classification, alerts and grouping of floods). I adopted it after the cost model rerun; Claude had added it as a review fix.

**Base building outside the lease (AD-25)**
- **Final:** a capture holds the repository lease only for the short work of fetching new objects. Building a new full base runs as a separate job from a copy of the cache. This keeps the simple design and separates the slow work from the time-sensitive work, so event captures still start within 15 minutes.
- I chose to settle this now instead of leaving it to the build, because the 15-minute start is an actual PRD requirement.

**Restored repositories (AD-26)**
- **Final:** restored repositories are discovered and backed up like any other repository.
- Deleting a restored repository whose content is already in the source repository's backups is routine, not an incident. Any new work in it makes it at-risk as normal.

**Vault alert acknowledgments (AD-27)**
- **Final:** security alerts raised in the vault are acknowledged in the vault, and the vault runs its own escalation sweep for them. Watchdog alerts repeat until their condition clears.

**Rewrites (AD-28)**
- **Final:** the notary works out rewrites itself, so a stolen worker credential can't hide a force-push by not reporting it. Merged-branch deletions are confirmed through the vault App (AD-29).

**Cost model assumptions**
- I kept most of Claude's starting assumptions and asked Claude to challenge mine.
- **Pushes:** 200 a day as the baseline, with 100 and 400 as sensitivity cases, because it's probably the assumption that affects cost most. LFS stays a separate line: 0 today, plus a scenario of three 5 GB files.
- **Rewrite events:** 1 a week as the base, because force-pushes and deletions are uncommon. After Claude's challenge I added 20 a week as a high case, because the real frequency depends a lot on how developers work.
- **Emails:** 20 a day, with 200 a day for a bad burst, because the number can rise a lot when failures and escalations happen.
- **Capture time:** 20 seconds at 2 GB of memory, with 10 and 40 seconds as sensitivity cases, to be measured in the build.
- **After the Challenge review:** I accepted five more assumptions (deleted repositories, daily records, notary speed, keeper requests, batch parallelism).

**Cost decisions**
- **The Graviton VM (final):** reconsider it as Orvex approaches 10×, using the capture time measured in the build. With B′, break-even is about 22 seconds per capture.
- **How it changed:** my first statement (at the time) was that the VM becomes cheaper at 10× (by about $15 a month) and should be reconsidered around that scale. The batch job was within cents of the pipeline then, and I kept the pipeline by my tie-break. After the rerun, I accepted a conditional statement with a break-even of about 18 seconds (at the time, with A). It is now about 22 seconds with B′.
- **Worker cache:** old versions are kept 1 day instead of 7. At the time this saved about $1.20 a month today and $12 at 10×.
- **Final figures:** B′ $9.58 a month today and $54.64 at 10×; A $10.14 and $61.06; B $9.43 and $54.47; D $24.28 and $57.94.

**Shared GitHub rate limit**
- **Final:** the daily batch job and event captures are not coordinated, the simplest option. Each waits when GitHub throttles it. The accepted risk is a delayed event capture during a big daily run plus a burst of pushes, to be measured in the build.

**Daily capture and event captures (FR-14, FR-66)**
- **Final:** the daily capture stays mandatory for every repository. An event capture never replaces it. The repository lease prevents them running at the same time.

**Finishing the deliverables**
- I removed the assignment PDF from the repository, because the assignment says no private Orvex information should be in it.
- I asked for the PRD to be updated so it matches the final architecture and decisions.
- **Six open items:** I first kept them as build-phase items and asked the Challenge review to check whether any of them violates a requirement or creates a serious security or reliability gap. Then I changed my mind and resolved them now:
  - restored repositories are backed up like any other repository (AD-26)
  - requesters reach the AWS restore copy through a single-use link (AD-18)
  - vault security alerts are acknowledged in the vault; watchdog alerts repeat until cleared (AD-27)
  - the vault watchdog sends the "no restore test passed by the 25th" alert (AD-13)
  - the best-effort fetch of overwritten commits is an accepted residual risk (AD-4)
  - the lifecycle build gate keeps a defined fallback (AD-7)

**Challenge step (adversarial review)**
- I ran the adversarial review on the architecture, cost model and runbook. It found 28 issues.
- For the six open items, it judged my resolutions sound but asked for about six guards:
  - a vault-side escalation sweep
  - the watchdog running at least every 15 minutes, plus a monitor
  - CloudTrail on the restore bucket
  - a rule for deleting restore destinations
  - validating the "before" commit before storing it
  - a pre-constrained fallback role, with a watchdog check
- I made four further decisions: routine deletion of restored repositories (AD-26), notary-derived rewrites (AD-28), the vault's own GitHub identity (AD-29), and verifying large additions before they move to Deep Archive (AD-3).
- I approved the remaining fixes and asked for the cost model to be rerun.

**Final review**
- I ran a final review of all deliverables with `bmad-review`, using five lenses: adversarial, edge cases, verification gaps, structure and prose. The findings are in `reviews/review-final.md` in the architecture folder.
- I approved applying all four batches of fixes: design correctness, numbers and cost model, AI_LOG accuracy, and editorial structure and prose.
- My FR-14/FR-66 decision (above) came from this review.
- **Restores without a UI, rechecked.** I asked whether "no request" works with no UI and only email links. It does: the person emails Strata, Strata checks their role and the email's authenticity, and they confirm through a single-use link, with no second person approving. Because everyone allowed to restore can already read that repository on GitHub, I kept the rule and changed the wording everywhere from "no request" to "no approval".
- **Four mechanisms from the final fixes, confirmed:**
  - the re-run controller starts every Fargate task, so the internet-facing capture role never holds permission to launch tasks
  - held records keep their hash chain back to the nearest checkpoint
  - bases under 128 KB stay in S3 Standard
  - the first-ever run is exempt from deadlines, and an overlap with the next scheduled start raises the normal alert

## Times I overruled Claude

Each is a case where Claude, or a review Claude ran, proposed one thing and I chose another. Where Claude's proposal was made in the session and not written to a log, the evidence says so.

**Brief session**

1. **Unanswered expiry warnings.**
   - *Claude:* extend retention and lock by another full 3 years.
   - *My decision:* extend only by the Glacier class's minimum storage period (90 or 180 days), to avoid paying for unused minimum storage, and warn again before it ends.
   - *Evidence:* brief log, `(override) ... overrides Claude's 3-year reading`.
2. **No fourth role.**
   - *Review:* add a fourth role.
   - *My decision:* rejected it; the second failure contact is another backup operator or an on-call person.
   - *Evidence:* brief log, "Polish (Maram): accepted 13 of 14 ... rejected adding a 4th role".
3. **Glacier wording.**
   - *Review:* proposed a wording for the Glacier minimum storage period.
   - *My decision:* reworded it myself: "Above the minimum storage period of the Glacier class in use: 90 days for Flexible Retrieval or 180 days for Deep Archive."
   - *Evidence:* brief log, "row 9 reworded by Maram".

**PRD session**

4. **A quiet day adds zero backup data.**
   - *Claude:* define "almost nothing" as a small allowance, for example $0.01 a month or 1 MB.
   - *My decision:* re-running a backup when nothing changed must not add data.
   - *Evidence:* session (Claude's proposal); PRD log, "Quiet-day rule", records my decision.
5. **No paging tool assumed.**
   - *Claude:* send urgent alerts through a paging or chat tool as well as email.
   - *My decision:* email only, because I don't know whether Orvex has such a tool.
   - *Evidence:* session (Claude's proposal); PRD log, "Alerts/messages: email only", records my decision.
6. **No fixed run hours.**
   - *Claude:* run at 02:00 UTC.
   - *My decision:* the requirement is "daily"; the PRD fixes no hours.
   - *Evidence:* session (Claude's proposal); PRD log, "Schedule: requirement is daily only", records my decision.
7. **Restores need no approval.**
   - *Claude:* repo owners, org owners or the backup operator request a restore, and the backup operator carries it out.
   - *My decision:* no approval is needed; repo owners, repo admins and org owners start a restore themselves by emailing Strata and confirming through a single-use link.
   - *Evidence:* session (Claude's proposal); PRD log, "Restores need no approval request", records my decision.
8. **Escalation must end with a decision-maker.**
   - *Claude:* if the budget owner doesn't answer, the org owner should only chase them, never approve.
   - *My decision:* then the chain has nobody with authority to decide, so an org owner may decide, but never on their own request.
   - *Evidence:* session (Claude's proposal); PRD log, "Follow-up D2", records my decision.
9. **Auto-extension lead time.**
   - *Review:* apply the auto-extension 14 days before the lock ends.
   - *My decision:* 7 days, keeping the 30-day warning as the main warning.
   - *Evidence:* session (the review's proposal); PRD log, "C2", records my decision.
10. **Routine deletions after a merge.**
    - *Review:* count a merged branch's deletion as routine only if it was merged into the default or a protected branch.
    - *My decision:* any branch that still exists.
    - *Evidence:* session (the review's proposal); PRD log, "C4", records my decision.
11. **Every repository must be backed up.**
    - *Claude:* a run fails as a whole only if discovery fails or more than 10% of repositories fail.
    - *My decision:* 100%; any failure triggers the re-run.
    - *Evidence:* session (Claude's proposal); PRD log, "M9 CHANGED by user", records my change.
12. **Restore destination.**
    - *Claude:* a new repository inside Orvex's GitHub org or AWS account.
    - *My decision:* Orvex's GitHub org (AWS only when GitHub is unavailable), with any move outside the org reported and alerted.
    - *Evidence:* session (Claude's proposal); PRD log, "Restore destination", records my decision.

**Architecture session**

13. **Chain limit.**
    - *Claude:* count 30 days with changes before starting a new full base.
    - *My decision:* 7 days with changes, for a shorter restore chain, faster recovery and less dependence on old objects.
    - *Evidence:* architecture log, "AD-2 amended".
14. **How backups get deleted.**
    - *Claude:* recommended that only Strata's own expiry step deletes backups, never an S3 lifecycle rule. I first accepted this.
    - *My decision:* after the Orvex contact asked me to define lifecycle rules, I switched to S3 lifecycle expiry because it's simpler and cheaper, and kept it only after verifying it against the tamper-resistance requirement.
    - *Evidence:* session (Claude's recommendation); architecture log, "AD-7 part 2 AMENDED", records my switch.
15. **Where alert and decision state lives.**
    - *Claude:* keep that state inside the workflow service (each alert as its own waiting workflow), with no new store.
    - *My decision:* a DynamoDB table in the worker account.
    - *Evidence:* architecture log, "D5".
16. **How often rewrite events happen.**
    - *Claude:* assume 5 rewrite events a week.
    - *My decision:* 1 a week as the base, because force-pushes and deletions are uncommon. I added 20 a week as a high case after Claude challenged it.
    - *Evidence:* architecture log, "Cost-model assumptions".
17. **How many emails Strata sends.**
    - *Claude:* assume about 40 emails a day.
    - *My decision:* 20 a day (the daily report, failure alerts, rewrite alerts and retention emails), with 200 a day as a burst case.
    - *Evidence:* architecture log, "Cost-model assumptions".
18. **When to reconsider the Graviton VM.**
    - *Claude:* revisit the VM when Orvex reaches around 5× growth.
    - *My decision:* reconsider it as Orvex approaches 10×, using the capture time measured in the build. With B′, break-even is about 22 seconds per capture.
    - *Evidence:* architecture log, "Cost decision 1" (Claude's 5× proposal) and "N4" (the final wording).
19. **The daily run's design.**
    - *Claude:* on 2026-10-06, after the recheck, recommended keeping the orchestrated pipeline (A) for everything.
    - *My decision:* B′, the hybrid: the daily backup runs as one batch job, with Step Functions kept for restore and event handling.
    - *Evidence:* session (Claude's 2026-10-06 recommendation); architecture log, "AD-1 AMENDED", records my switch to B′.
20. **Sharing GitHub's rate limit.**
    - *Claude:* a shared token bucket that gives event captures priority over the daily run.
    - *My decision:* leave them uncoordinated, the simplest option. Each respects GitHub's limits.
    - *Evidence:* architecture log, "Shared GitHub rate limit".
