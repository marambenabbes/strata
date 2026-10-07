---
title: "PRD: Strata — GitHub org backup on AWS"
status: final
created: 2026-10-04
updated: 2026-10-07
inputs:
  - assignment brief (held outside the repository, not published; source of truth where stated)
  - _bmad-output/planning-artifacts/briefs/brief-repo-backup-service-2026-09-29/brief.md (final; decisions not reopened)
  - _bmad-output/planning-artifacts/briefs/brief-repo-backup-service-2026-09-29/addendum.md
  - _bmad-output/planning-artifacts/briefs/brief-repo-backup-service-2026-09-29/.memlog.md
  - _bmad-output/planning-artifacts/architecture/architecture-repo-backup-service-2026-10-05/ARCHITECTURE-SPINE.md (user-approved; 2026-10-07 updates align this PRD with AD-1..AD-29, including the Challenge-review decisions)
---

# PRD: Strata — GitHub org backup on AWS

## 0. Document purpose

This PRD is for the engineers who will design, build and run Strata. It turns the final product brief and the Orvex AI assignment into testable requirements. **The brief's decisions are final and are not reopened here.** Where the brief left a point open, this PRD closes it; each such decision was made with the product owner (Maram) and recorded in this run's `.memlog.md`.

How to read it:

- **§3 Glossary** fixes the vocabulary. FRs use Glossary terms exactly; do not introduce synonyms.
- **§4 Features** group the functional requirements. FRs are numbered globally (FR-1 … FR-67) so architecture, epics and tests can cite stable IDs. Each FR has testable consequences.
- **IDs are stable, not in reading order.** FR, NFR, COST, SM, UJ and Q IDs are never renumbered; later additions (for example FR-55–FR-67) sit in the section they belong to.
- **§5–§6** hold cross-cutting non-functional requirements and the cost requirements.
- **§13** lists the assumptions the product owner has confirmed.
- **This PRD states what Strata must do, not how.** Mechanism choices (GitHub App vs token, S3 Object Lock mode, storage classes, compute, acknowledgment mechanism) belong to the architecture. Known technical directions and rejected alternatives are collected in `addendum.md` next to this file.

Downstream artifacts required by the assignment: architecture document with diagrams, cost model with every assumption stated, restore runbook for one repo on one date, `AI_LOG.md`, and a README.

## 1. Vision

Strata is a daily, unattended backup of every repository in Orvex AI's GitHub org, kept in Orvex's own AWS account. Nearly all of Orvex's value is its code and that code's history. GitHub hosting the code is not the same as Orvex having a backup of it, and laptop clones are partial, fragile, lose rewritten history and cannot prove what they hold.

Strata stores only what changes each day. It keeps commits lost to force-pushes and deletions, and it rebuilds any repository exactly as it was on any backed-up day, into a new repository, without needing GitHub. Nobody, including the person who runs it, can delete or change existing backups. Routine snapshots are kept and locked for at least 1 year and then expire automatically; data that newer backups still need stays locked for as long as they need it. Data that exists in no newer backup is kept and locked for 3 years and only removed after a person decides; an unanswered warning keeps the data.

Strata guards against four losses: a repository deleted by mistake or on purpose; a leaked token used to destroy or rewrite code; a force-push that overwrites a branch's history; and a bug found long after it was introduced, needing an old state to investigate.

Strata guards against two failures: **GitHub losing data** (the disaster it exists for) and **Strata failing quietly** (which leaves Orvex unprotected when that disaster comes). Every failure is loud. Every morning an email says what happened; every failure raises an alert that escalates until someone with authority acknowledges it.

**Why build rather than buy.** Strata is not better than existing products: Rewind and GitProtect already cover these requirements. Orvex builds for **control** (own backups, security model, retention rules and cost, in its own AWS account, with no vendor that could be breached, change terms or shut down) and **independence from GitHub** (GitHub's branch protection and 90-day deleted-repo restore are controlled by the same accounts an attacker would target). The price of control: Orvex owns the AWS bill, GitHub rate limits, security, alerting and restore testing. These requirements exist to pay that price deliberately.

## 1a. Goals

1. **Nothing in a completed backup is ever lost** before its retention ends, whatever happens on GitHub or to Strata's credentials.
2. **Any repository can be rebuilt** exactly as it was on any backed-up day, without GitHub, by a documented and tested procedure.
3. **No failure is silent.** Every failure reaches someone who can act.
4. **The simplest and cheapest design that meets every requirement.** The architecture must justify both: why the chosen design is the cheapest (COST-1) and why it is the simplest design that works (COST-8).

Goals 1–3 come from the assignment ("Keep rewritten history", "Restore to any day", "Fail loudly", "nothing lost"); goal 4 from its judging criteria ("the simplest design that works", "the cheapest design that works"). The brief adds who decides what (§2.1) and the retention rules (§4.6).

## 2. Users and roles

Strata has **no user interface**. People interact with it through email: a daily email, a monthly cost email, and alerts that ask them to act. Roles are split by knowledge: the repo owner knows how important the code is, the budget owner knows Orvex's financial situation, and the backup operator knows how Strata, AWS and GitHub work. Roles are not tied to Orvex job titles, which are not yet fixed.

### 2.1 Roles

| Role | Who | Responsible for | Cannot |
|---|---|---|---|
| **Backup operator** | A DevOps engineer | Keeping Strata running daily: triggering backup runs, investigating failures, retrying failed backups, performing restores, running restore tests, carrying out approved extensions. Holds AWS and GitHub access to investigate and restore. | Delete or change backups or run records, weaken their protection, request or approve an extension, or act alone on retention. |
| **Second failure contact** | Another backup operator or an on-call person | Receiving the daily email, and the backup-failure and security alerts that the backup operator has not acknowledged; triggering retries and backup runs. | Same limits as the backup operator. |
| **Repo owner** | The GitHub team(s) assigned to the repository | Investigating rewrite events on their repos; requesting extensions (primary requester) or letting at-risk data expire; initiating restores. | Approve an extension. |
| **Repo admin** | Users with admin rights on the repository in GitHub | Second step of the repo-alert escalation chain; stand-by requester of extensions; initiating restores. Acts as repo owner when the repo has no assigned team. | Approve an extension. |
| **Org owner** | A GitHub organization owner | Last step of every repo-alert and budget escalation chain. As **stand-in repo owner**: can investigate and request an extension, cannot approve it. As **stand-in budget owner** (only after a budget escalation, and only if they are not the requester): can approve or deny the extension. Initiating restores. | Approve its own request; shorten a lock; delete a backup. |
| **Budget owner** | The person responsible for infrastructure costs | Approving or denying extension requests; receiving the monthly cost email. | Shorten a retention period or lock (nobody can). |

Extending retention always involves separate people: **repo owner requests → budget owner approves → backup operator carries it out.** The requester and the approver are always different people. The person with technical control (the backup operator) cannot act alone on retention: they never request or approve; they only carry out. Each decision is made by the role that understands it (code, money, system), which adds security and traceability.

**Message routing**

| Message | Goes to |
|---|---|
| Daily email | Backup operator and second failure contact |
| Rewrite-event alerts | Repo owner of the affected repo (escalation per FR-47) |
| Ownership-change alerts | Previous repo owner of the affected repo (escalation per FR-47, FR-57) |
| Expiry warnings | Repo owner of the affected repo |
| Extension requests and monthly cost email | Budget owner |
| Backup-failure and security alerts | Backup operator, then second failure contact (escalation per FR-47) |
| No-owner-repository alerts | Repo admins of that repo (escalation per FR-47) |

### 2.2 Jobs to be done

- **Backup operator:** "Tell me every morning whether every repo is safe, and wake me up the moment it isn't — without making me the person who could destroy the backups."
- **Repo owner:** "If someone rewrites or deletes our history, tell us within the hour and let us get the old commits back into a fresh repo we can inspect."
- **Repo owner / repo admin:** "When a bug turns up months after it shipped, let us rebuild the repo exactly as it was on that day."
- **Budget owner:** "Show me what backups cost and how that is growing, and let me decide when keeping old data longer is worth the money."
- **Orvex:** "Recovery must never depend on luck, on one person's laptop, or on GitHub still being reachable."

### 2.3 Non-users (v1)

People outside Orvex's GitHub org, and anyone needing issue, pull-request or release history or a web UI, are not served by v1; the exclusions are listed in §8.2.

### 2.4 Key user journeys

Names are illustrative.

**UJ-1. Sam, the backup operator, checks the morning email.**
Sam opens the daily email before stand-up. It says the run finished on time, 93 repos were checked, 2 new repos were discovered and backed up, 11 repos changed, storage grew by 18 MB, one repo needed two retries before succeeding, nothing failed, yesterday's spend was a few cents, and one repo still has no owner team. Sam forwards the no-owner line to the repo's admins and is done in a minute. **Edge case:** on a day with no pushes at all, the email still arrives and says "0 bytes of new backup data; run record written" — silence never stands in for "all fine". Realizes FR-1, FR-8, FR-9, FR-12, FR-49, FR-50.

**UJ-2. Priya's team learns of a force-push within the hour and recovers the old commits.**
At 14:10 someone force-pushes `main` in `payments-api`, dropping three days of commits. Within minutes Strata emails Priya's team (the repo owner): repo, branch, before and after commit IDs, who pushed if GitHub says, and that the event capture saved the overwritten commits. Priya acknowledges from the email. Her team decides the push was a mistake and initiates a restore of `payments-api` as it was just before the event into a new repository, inspects it, and pushes the lost commits back themselves. **Edge case:** if the event capture failed (GitHub no longer served the old commits), the alert says so plainly and states which backed-up day last holds the branch; commits created and overwritten between the last run and the event are reported as not recoverable. **Edge case:** if Priya's team does not acknowledge in 1 hour, the alert goes to all repo admins, then to an org owner. Realizes FR-16–FR-21, FR-35–FR-38, FR-46–FR-48.

**UJ-3. Omar, a repo admin, investigates a bug introduced eight months ago.**
A customer reports a calculation bug that has existed since spring. Omar initiates a restore of `pricing-engine` as of a day in February. Strata rebuilds it — branches, tags, exact commit IDs, LFS files and wiki — into a new repository and reports that the restore verified against that day's run record. Omar bisects in the restored copy without touching the live repo. Realizes FR-35–FR-41.

**UJ-4. A deleted branch's commits approach the end of their 3-year retention.**
Thirty days before at-risk data from a deleted experiment branch expires, Strata warns the repo owner. Lena, on that team, acknowledges and requests a 180-day extension because the experiment may be revived. The budget owner acknowledges within 24 hours, reviews the cost shown in the request over the following week, and approves. Sam triggers the approved extension, which Strata applies only after checking the recorded approval; retention and lock both move out by 180 days. **Edge case:** if the budget owner never acknowledges, the request escalates to an org owner (not the one who requested), who can decide. If nobody decides before the lock ends, Strata extends retention and lock by the Glacier minimum storage period, reports the extra storage, and warns again. Realizes FR-28–FR-33.

**UJ-5. A backup fails overnight and still reaches someone who can act.**
GitHub returns errors for one large repo. Strata retries it with increasing delays; the other 92 repos finish normally. Retries run out, so Strata alerts Sam. Sam is on leave and does not acknowledge within 1 hour; the alert escalates to the second failure contact (the on-call person), who acknowledges, finds a transient GitHub incident and triggers a retry that succeeds. The next daily email lists the failure, every retry, the escalation and the acknowledgment. Realizes FR-12–FR-15, FR-45–FR-48, FR-56.

**UJ-6. The monthly restore test proves the backups work.**
Once a month a restore test rebuilds a repository as of a past backed-up day, including one where a rewrite event happened, and checks every branch, tag, commit ID, LFS object and wiki page against the run record. The result appears in Sam's daily email the next morning; a failed test is a backup-failure alert to Sam, who investigates before trusting that repository's backups. Realizes FR-42, FR-43.

## 3. Glossary

- **Org** — Orvex AI's GitHub organization. The only source Strata reads from.
- **Repository (repo)** — Any repository owned by the org, whatever its visibility, archived state or fork status. Its **wiki** is backed up with it. One org has many repositories.
- **Ref** — A branch or tag in a repository. Each ref points at one commit ID.
- **Backup run** — One scheduled, unattended daily execution of Strata over the whole org. Exactly one backup run is scheduled per day.
- **Event capture** — A best-effort, single-repository capture triggered by every push and every repository-created event, in addition to the backup run. On a rewrite event it also tries to save the overwritten or removed commits (FR-18).
- **Run record** — The small, locked record a backup run writes on every day it runs, quiet or not: which repos and refs it checked, the commit ID of every ref, what was new, what failed, every retry, rate-limit wait and alert. Also written for event captures (the architecture calls an event capture's record a capture record).
- **Backup data** — Stored Git objects, LFS objects and wiki content. Run records, the audit trail and event metadata are not backup data.
- **Backup** — Backup data plus the run record that describes it, for one repository and one backed-up day or event capture.
- **Completed backup** — A backup whose run record shows the repository was successfully backed up and verified against GitHub's refs (FR-2). Strata's central guarantee applies to completed backups.
- **Day** — A calendar day in UTC. All dates in Strata (backed-up days, retention, expiry) are UTC days.
- **Backed-up day** — A day for which a run record exists that shows a repository was successfully checked. A repository can be restored as of any backed-up day still within retention.
- **Quiet day** — A day on which no repository received any push or rewrite.
- **Rewrite event** — Any of: a **force-push** to a branch, a **branch deletion** that is not a routine branch deletion, a **tag move**, a **tag deletion**, or a **repository deletion**. Rewrite events are incidents.
- **Routine branch deletion** — A branch deletion that loses no work (FR-55): every commit on the branch is reachable from another ref, or the branch was the head branch of a pull request GitHub shows as merged and was deleted at exactly the merged commit. Never the default branch or a protected branch. Not a rewrite event.
- **Routine snapshot** — The backup of one backed-up day, together with content that still exists in a newer backup or whose commits were removed only by a routine branch deletion that Strata's own backups prove loses no work (FR-55 rule 1), or that the protected backup account has confirmed with GitHub as merged (FR-55 rule 2). Retention class: kept at least 1 year from its backed-up day. Any stored object a routine snapshot needs is kept for as long as any backup within retention depends on it (FR-32).
- **At-risk data** — Backed-up content that exists in no newer backup because of a rewrite event, for example commits lost to a force-push or to deletion of an unmerged branch. Retention class with a 3-year retention period.
- **Retention period** — How long a backup is kept. Equal to its lock. For a stored object, it ends only when no backup within retention depends on it any more.
- **Ownership snapshot** — The repo owners, repo admins and org owners recorded in the last locked run record before an event. Used to route alerts and to check who may acknowledge or decide (FR-57).
- **Lock** — Protection that prevents anyone, including administrators and the AWS account root user, from deleting, changing or shortening protection of a backup until it ends. Can be extended, never shortened.
- **Expiry** — The end of a backup's retention period, after which it is removed.
- **Expiry warning** — The message telling a repo owner that at-risk data will expire.
- **Extension** — A lengthening of the retention period and lock of at-risk data, requested by a repo owner and approved by the budget owner.
- **Dependency extension** — Strata keeping a stored object locked for as long as a backup within retention depends on it: the object stays held while newer backups still need it and is then locked for at least 1 more year (FR-32). It never shortens a lock.
- **Auto-extension** — The extension Strata applies by itself when an extension decision is not made before expiry: 180 days (the Glacier minimum storage period), for every at-risk object whatever its storage class.
- **Glacier minimum storage period** — The minimum billed storage duration of S3 Glacier Deep Archive, the class Strata uses for long-term backups: 180 days. Backup objects kept in S3 Standard (NFR-P3) use the same period for extensions.
- **Alert** — An email that requires acknowledgment. Has a class with an acknowledgment deadline.
- **Acknowledgment** — A recipient's confirmation that they have seen an alert. Stops escalation of that alert only. It is not a decision.
- **Acknowledgment deadline** — The time after which an unacknowledged alert escalates (1 hour or 24 hours). Distinct from any decision deadline.
- **Escalation chain** — The ordered list of recipients an alert moves through until acknowledged. Every chain ends with someone who has authority to decide.
- **Restore** — Rebuilding a repository as of a backed-up day (or an event capture) into a **new repository**.
- **Restore test** — A scheduled restore whose result is verified and reported.
- **Expected end** — The configured time by which a backup run should have finished. Used to detect late runs (FR-15).
- **Daily email** — The report sent after every backup run to the backup operator and the second failure contact.
- **Monthly cost email** — The cost report sent each month to the budget owner.
- **Audit trail** — The tamper-resistant record of every Strata operation and every human decision.

## 4. Features and functional requirements

### 4.1 Repository discovery and coverage

**Description:** Every backup run finds every repository the org owns, including ones created since the last run, and backs up all of their Git data, LFS objects and wiki. Nobody maintains a list. Ownership is read from GitHub on every run so alerts reach the right team without manual upkeep.

#### FR-1: Automatic discovery of every repository
Every backup run discovers all repositories owned by the org.

**Consequences (testable):**
- When Strata receives a repository-created event, or a push to a repository not yet backed up, it starts an event capture of the new repository (FR-18), so it is backed up within minutes. The next backup run includes it in any case, so a missed event still leaves it backed up within 24 hours of creation.
- Private, internal, public, archived, forked and empty repositories are all included, and so are repositories created by restores (FR-35).
- The run record lists every discovered repository; the daily email states the count and names newly discovered repositories.
- A repository that is discovered but cannot be backed up is a failure (FR-12), never silently skipped.

#### FR-2: All refs and their history
Each backup run backs up every branch and every tag of every repository, with all commits reachable from them.

**Consequences (testable):**
- For each repository, the run record holds the name and commit ID of every ref at the time of the run.
- Each backup run checks the refs it recorded against GitHub's own list of refs for the repository at that time; any mismatch is a failure (FR-12). The run record therefore states what GitHub had on that day.
- Every commit reachable from any recorded ref is restorable (FR-36).
- An empty repository or an enabled but empty wiki is recorded as successfully backed up with zero refs; it is not a failure.
- For tags, the run record holds the tag's own object ID as well as the commit it points to.

#### FR-3: Wikis
Each backup run backs up the wiki of every repository that has one, with its full history. Wikis are in scope because they hold important information about each project.

**Consequences (testable):**
- A restore includes the wiki as it was on the chosen backed-up day.
- A rewrite of wiki history is detected and treated as a rewrite event on that repository.
- GitHub sends no live events for wikis, so wiki rewrites are detected by the backup run (FR-19) and never count as missed live events.
- A wiki is recorded as empty only when GitHub's repository data and the wiki clone agree that it has no content; any other clone failure is a backup failure.

#### FR-4: Git LFS objects
Strata backs up every Git LFS object referenced by any backed-up commit, with no limit on file size or type.

**Consequences (testable):**
- Orvex does not use LFS today. When any repository starts using LFS, its LFS objects are backed up by the next backup run with no configuration change or redesign.
- An LFS object referenced by a commit but missing on GitHub is recorded as "unavailable at source", listed in the daily email and checked again on every run. It does not fail the repository, because a re-run cannot fix it.
- An LFS object already stored is never stored again. A changed LFS file is stored again in full (LFS versions whole files).
- LFS storage and transfer are reported as a separate line in the daily email and monthly cost email.

#### FR-5: Repository ownership read from GitHub
Each backup run reads, for every repository, the GitHub team(s) assigned to it and its repo admins, and records them in the run record.

**Consequences (testable):**
- The repo owner is the GitHub team assigned to the repository. If several teams are assigned, all of them are repo owners.
- `CODEOWNERS` and hand-maintained lists are not used.
- A repository with no assigned team is listed in every daily email and raises a no-owner-repository alert (FR-45). Until a team is assigned, its repo admins act as repo owner.
- For a deleted repository, the repo owner and repo admins are those in the last run record that included it.
- Live GitHub ownership is recorded but never trusted on its own for alerts or decisions; the ownership snapshot is used instead (FR-57).

#### FR-59: Repositories are identified by GitHub ID
Strata identifies each repository by its GitHub repository ID across runs, not by its name.

**Consequences (testable):**
- Each run record keeps every repository's ID and current name; name history is kept.
- A rename is not an incident. It is listed in the daily email, and restores can find the repository by any of its names. If a name has belonged to more than one repository, Strata lists the candidates and the restore request must name the repository ID.
- A repository deleted and then recreated with the same name is two different repositories: the deletion is a rewrite event and the new repository is backed up as new.
- A transfer of a repository out of the org is a rewrite event (repository deletion from Orvex's point of view) and is alerted as such. If it is transferred back, that is alerted too; its backups continue, and its earlier at-risk classifications and pending decisions are kept.

#### FR-60: Deletion is confirmed, not inferred
A repository is treated as deleted only when GitHub confirms it.

**Consequences (testable):**
- A repository missing from discovery is marked deleted only after a direct lookup of that repository confirms it no longer exists, or a repository-deletion event was received.
- If any repository in the previous run record is missing from discovery without a confirmed deletion, the run fails (FR-12, FR-56) instead of recording a deletion, consistent with the rule that every discovered repository must be backed up.
- Any change to Strata's GitHub access (its installation, permissions or repository selection) raises a backup-failure alert.

#### FR-6: No repository is too big
Strata backs up a repository regardless of its size or history length.

**Consequences (testable):**
- The architecture names the largest repository and LFS object it has been tested with and how it handles a repository that exceeds the limits of its default compute.
- A repository that cannot be backed up because of its size is a failure (FR-12), never skipped.

### 4.2 Daily backup run and incremental storage

**Description:** A backup run happens every day with no person or laptop involved. It stores only what is new since the last backup, so a quiet day adds no backup data. Every run, quiet or not, writes a small locked run record that proves it happened, says exactly what it checked, and records any problem.

#### FR-7: Daily, unattended
Strata runs one backup run every day, on a schedule, with no human action.

**Consequences (testable):**
- The run start time and the expected end are configuration, not fixed by this PRD.
- No step of a backup run requires a person, a laptop, or a personal credential (NFR-S2).

#### FR-8: Store only what changed
A backup run stores only data that is not already stored.

**Consequences (testable):**
- A Git object or LFS object already in Strata's storage is not stored a second time, with one exception: after a repository's backups have changed on 7 days, the next backup on a day with changes stores a new full copy of the repository, so that a restore never depends on a long series of earlier backups. This full copy is written only on a day with changes, never on a quiet day. LFS objects are never stored twice.
- **A quiet day adds 0 bytes of new backup data.** The only new storage on a quiet day is that day's run record and its audit trail entries.
- Re-running a backup run when nothing changed adds 0 bytes of new backup data.

#### FR-9: Run record for every run
Every backup run writes a run record, whether it succeeds, partly fails or fails.

**Consequences (testable):**
- The run record contains at least: run ID; scheduled, start and end times; every discovered repository; for each repository, its GitHub ID and name (FR-59), every ref and its commit ID (and tag object ID), its wiki's state, whether it changed, what was newly stored, and the repo owner and repo admins (FR-5); every rewrite event detected (FR-19); every failure, retry and rate-limit wait (FR-12, FR-13); every alert sent during the run, with a reference to the audit trail where later acknowledgments and escalation steps are recorded (FR-46); bytes of new backup data written.
- The run record is locked like a backup (FR-22) and kept at least as long as any backup that relies on it to be restored (FR-32).
- The run record's size depends on the number of repositories and refs, not on the size of the code.
- A run that fails part-way still writes a run record stating how far it got and why it stopped.

#### FR-10: Every backed-up day is restorable
For every backed-up day within retention, Strata holds everything needed to restore each successfully checked repository exactly as it was in that day's run record.

**Consequences (testable):**
- For any repository and backed-up day, Strata can list the refs and commit IDs that a restore will produce, from the run record alone, before restoring.

#### FR-11: Catch-up after a gap
If a repository was not backed up on a day (failure or missed run), the next successful backup run captures everything that changed since that repository's last successful backup.

**Consequences (testable):**
- No content that still exists on GitHub is missing from Strata after the next successful run.
- Days with no successful backup of a repository are shown as gaps in the run record and daily email; they are not backed-up days for that repository.

#### FR-65: One backup run at a time, one record per day
Backup runs never overlap, and each day is represented by one run record.

**Consequences (testable):**
- A day is a UTC day. A run that crosses midnight belongs to the day it was scheduled for.
- If several backup runs complete on one day (for example after a re-run, FR-56), the day is represented by the last successful run record.
- Rewrite detection (FR-19) compares each repository with its last successful run record, however old.
- Two backup runs never run at the same time; an attempted overlap is prevented and raises a backup-failure alert.

### 4.3 Run reliability: retries, rate limits and missed runs

**Description:** Transient failures and GitHub's rate limits are normal. Strata absorbs them automatically, without letting them hide: a repository is retried before it is declared failed, one bad repository never stops the others, rate limits slow a run down rather than fail it, and if a run is late, fails, or never starts, someone hears about it. Realizes UJ-5.

#### FR-12: Automatic retries with isolation
Strata retries a failed repository backup automatically, with increasing delays, before declaring it failed.

**Consequences (testable):**
- The number of attempts and the delays are configuration. Default: 3 attempts with exponential backoff, all within the run's window to the expected end.
- A failure of one repository never stops the backup of other repositories.
- Strata sends a backup-failure alert (FR-45) only when retries for a repository are exhausted.
- Every retry, including retries that later succeeded, is recorded in the run record and listed in the daily email, so unreliable repositories are visible.
- The backup operator or the second failure contact can trigger a manual retry of a failed repository; it is recorded like any other operation.
- A failure that repeats for the same repository and cause on 3 consecutive days is listed as persistent in the daily email.

#### FR-13: Respect GitHub rate limits
Strata respects GitHub's primary and secondary rate limits.

**Consequences (testable):**
- When GitHub signals a rate limit, Strata pauses and resumes after the period GitHub indicates instead of failing or retrying immediately.
- Rate-limit waits are recorded in the run record with their duration and shown in the daily email.
- A rate limit alone is not a failure. If waiting makes the run late, the backup-failure alert for a late run (FR-15) still fires.

#### FR-14: Event captures share limits safely
Event captures (FR-18) and restores (FR-35) respect the same rate limits and never cause a backup run to fail or be skipped.

**Consequences (testable):**
- An event capture and a backup run touching the same repository at the same time both complete without corrupting or duplicating stored data.
- Every backup run backs up every repository itself. An event capture never counts as, or replaces, a repository's backup in the backup run.

#### FR-56: Automatic re-run of a failed run
When a backup run fails, never starts or never finishes, Strata alerts and automatically starts the run again once.

A backup run succeeds only if **every discovered repository** is successfully backed up. If even one repository fails after its retries (FR-12), or discovery fails, the run has failed.

**Consequences (testable):**
- The first failure raises a backup-failure alert and triggers one automatic re-run, covering the repositories that failed (or the whole run if discovery failed or the run never started).
- The re-run finishes or is cancelled before the next scheduled backup run starts and never overlaps it (FR-65).
- A run that is merely late is not re-run while it is still progressing; it is re-run only if it fails or stops.
- If the re-run also fails, Strata alerts again and the alert escalates normally (FR-47). There is no further automatic re-run that day.
- Both attempts and their outcomes are recorded in the run record and the daily email.

#### FR-15: Missed, failed or late runs are always reported
A watchdog that does not depend on the backup run itself alerts when a backup run has not completed.

**Consequences (testable):**
- A backup run that fails raises a backup-failure alert as soon as it fails, without waiting for the expected end.
- If no successful run record for the day exists 1 hour after the expected end, a backup-failure alert is sent; when the first attempt failed and a re-run is due, the alert waits until 1 hour after the re-run's deadline. This covers a run that never started, never finished, or failed.
- The watchdog alerts even if the backup run's own compute, schedule or code is broken.
- A run that completed with failed repositories raises backup-failure alerts for those repositories (FR-12).

### 4.4 Rewrite events: detection, alerting and capture

**Description:** The assignment requires that when a branch is force-pushed or deleted, its old commits stay recoverable and the event is flagged. Strata does this in three layers. **(1)** It listens for rewrite events from GitHub as they happen and sends one alert per event to the repo owner. **(2)** On every push it immediately attempts an event capture of the affected repository, so new commits are normally stored before a later force-push can overwrite them; on a rewrite event the capture also tries to save any overwritten commits not yet stored, if GitHub still serves them. **(3)** Every backup run compares each repository's refs with the previous run record, so a rewrite whose event was missed is still detected and flagged. The **daily backup run is the guarantee**: every commit in any completed backup stays recoverable. The event capture is **best effort** and narrows the gap between runs; its result is always reported. Realizes UJ-2.

Not every branch deletion is an incident. Deleting a branch after its work was merged is routine and must not create alert spam or 3-year retention. Strata classifies each branch deletion (FR-55): routine branch deletions are reported quietly in the daily email; every other deletion is a rewrite event.

Known limit: commits created and overwritten between two backup runs are recoverable only if the event capture succeeds. A repository created and deleted between two backup runs is not recoverable. These follow from the daily cadence the assignment requires.

#### FR-16: Listen for rewrite events
Strata receives push, repository-created, force-push, branch deletion, tag move, tag deletion and repository deletion events from GitHub as they happen, for every repository in the org, and classifies each branch deletion (FR-55).

**Consequences (testable):**
- A rewrite event in any repository, including one created since the last backup run, is received without per-repository setup.
- Events that cannot be authenticated as coming from GitHub are rejected. They are counted per source and hour (not stored individually in locked storage), and a spike raises a security alert (FR-64).

#### FR-17: One alert per rewrite event
Each rewrite event produces its own alert to the affected repository's repo owner.

**Consequences (testable):**
- Strata sends the alert within 15 minutes of receiving the event.
- Two force-pushes to the same branch on the same day produce two alerts (subject to flood grouping, FR-66).
- A routine branch deletion produces no alert (FR-55).
- The alert states: repository; ref; event type; time; before and after commit IDs; the GitHub user who caused it if GitHub provides it; whether the old commits are already in a completed backup and as of which backed-up day; and the event capture result (FR-18). If the capture result is not known in time, the alert says the capture is pending and a follow-up reports the result.
- The alert states that backups are safe and that the concern is the live repository.
- Alert class: rewrite event, acknowledgment deadline 1 hour (FR-45).

#### FR-18: Best-effort event capture
On every push and every repository-created event, Strata immediately attempts an event capture of the affected repository. On each rewrite event other than repository deletion, and on each routine branch deletion, the event capture also attempts to save the commits the event overwrote or removed, if they are not already stored.

**Consequences (testable):**
- The event capture starts within 15 minutes of Strata receiving the event, and captures the commit IDs named in the event, not whatever the branch points at when the capture runs.
- An event capture stores only data not already stored (FR-8) and writes a run record (FR-9).
- Its result — succeeded, partly succeeded or failed, with which commits were saved — is included in the event's alert (rewrite events only), the run record and the daily email. A failed event capture is never silent.
- Content saved by an event capture is protected (FR-22) and classified (FR-20) like any other backup, and can be restored (FR-37).
- The backup run does not depend on event captures; if the event listener or event captures are down, the backup run still runs and still detects rewrites (FR-19).
- Because every push is captured, the best-effort fetch only matters for commits pushed and overwritten within minutes; this is an accepted residual risk, measured by SM-9.

#### FR-19: Rewrite detection in every backup run
Every backup run compares each repository's refs with the previous run record and detects rewrite events.

**Consequences (testable):**
- A ref whose new commit does not contain its previous commit is detected as a force-push or tag move; a missing ref as a branch or tag deletion, classified per FR-55; a missing repository as a repository deletion.
- A rewrite event detected by the backup run with no matching event from FR-16 raises an alert (FR-17) marked "detected by daily run; no live event received", and the missed event is recorded.
- Every rewrite event and every routine branch deletion, however detected, is listed in the daily email.
- A ref's tag object ID changing is a tag move, even if it points at the same or a later commit.
- Renaming the default branch (GitHub reports the rename and the same commit appears under the new name) is a rename, not a deletion.
- A branch deleted and recreated with the same name between two backup runs is still detected as a deletion, from the event captures in between.
- An event matches a backup-run detection when the repository ID, ref and before/after commit IDs agree. Late or out-of-order events are recorded but never alerted as new incidents twice.
- Each backup run checks that the event subscription exists and is correctly configured. A configuration change, or two consecutive rewrite events detected only by a backup run, raise a backup-failure alert. The listener's health is shown in the daily email.

#### FR-20: Classify at-risk data
Content that exists in no newer backup is classified as at-risk data.

**Consequences (testable):**
- Commits (and their trees, blobs and LFS objects) that are no longer reachable from any ref recorded in the latest run record because of a rewrite event are classified as at-risk data when the rewrite is detected.
- Commits removed only by a routine branch deletion stay routine snapshots: kept and locked for at least 1 year, then expire automatically (FR-26). They remain restorable for that time.
- All content of a deleted repository is classified as at-risk data, with one exception: deleting a repository that Strata created as a restore destination (identified by its repository ID in Strata's own restore evidence, never by its name) is a routine deletion when everything in it is already held in the source repository's backups. It raises no alert and creates no at-risk data. If the restored repository received any new work, its deletion is at-risk as normal. Making a restored repository public or moving it out of the org still raises the FR-35 security alert.
- Whether content is at-risk is decided from Strata's own backups and from GitHub facts that the protected backup account checks itself, never from what a single component reports. A merged pull request (FR-55 rule 2) shortens retention only when the protected account has confirmed it directly with GitHub; otherwise it may prevent an alert but never shortens retention.
- Content whose classification failed or is unknown is treated as at-risk data. A failed classification raises a backup-failure alert.
- At-risk data is kept and locked for 3 years from classification (FR-27).

#### FR-21: Prove old commits survive
For any rewrite event, Strata can prove that the old commits survive.

**Consequences (testable):**
- For a given rewrite event, the backup operator can obtain, without GitHub access, the list of old commit IDs that are held in Strata and a restore that contains them (FR-37).
- The restore test (FR-42) includes at least one rewrite event when one exists within retention.

#### FR-55: Routine branch deletions are not incidents
Strata classifies every branch deletion as either a routine branch deletion or a rewrite event.

A branch deletion is **routine** only if one of these holds:
1. Every commit on the branch at deletion is reachable from a branch or tag that **still exists after all deletions and rewrites in the same window**, and is recorded in the new run record (for example after a normal merge). Refs Strata does not back up (such as pull-request refs) do not count.
2. The branch was the head branch of a pull request that GitHub shows as merged into a branch that **still exists and contains the merged result**, and the branch was deleted at exactly the commit that was merged (covers squash and rebase merges).

And, in every case, the deletion was **both received as a live event (FR-16) and confirmed by the backup run (FR-19)**. Wiki branches are exempt from the live-event part, because GitHub sends no wiki events (FR-3).

**Consequences (testable):**
- Deleting the default branch or a protected branch is always a rewrite event, whatever its merge state.
- Deleting a branch with commits that were never merged is a rewrite event, including abandoned branches deleted as cleanup.
- Deleting a branch that received commits after its pull request was merged is a rewrite event.
- A branch deletion detected only by the backup run, with no matching live event, is a rewrite event, so a disabled event listener cannot hide deletions as routine.
- **Bulk deletion:** more than 5 branch deletions in one repository within one hour or within one backup run's comparison window make every one of those deletions a rewrite event, reported as a bulk deletion; deletions already classified as provisionally routine in that window are reclassified and alerted. The threshold is configuration; it cannot be raised above 5 without an audited change.
- Several branches deleted together cannot make each other routine: reachability is checked only against refs that still exist.
- A routine branch deletion raises no alert. It creates no at-risk data when rule 1 holds, because Strata's own backups prove the commits are still held. A deletion that is routine only by rule 2 also raises no alert; its commits are kept as routine snapshots (1 year) when the protected backup account has confirmed the merge directly with GitHub, and as at-risk data (FR-20) otherwise. Either way it is listed in the daily email with per-repository counts, so an unusual spike is visible.
- Deleting a repository that Strata created as a restore destination is covered by FR-20, not by this rule.
- If Strata cannot determine a deletion's merge state (for example GitHub data is unavailable), it treats the deletion as a rewrite event.
- **Provisional classification:** when the live event arrives, Strata applies rules 1 and 2 against GitHub's current state. A deletion that fails them is a rewrite event and is alerted within 15 minutes (FR-17). A deletion that passes them raises no alert and is recorded as *provisionally routine*.
- The next backup run rechecks every provisionally routine deletion. If the recheck confirms it, it becomes a routine branch deletion. If the recheck does not confirm it, Strata raises a rewrite-event alert, records the deletion as an incident and classifies its commits as at-risk data (FR-20).
- While a deletion is provisionally routine, its commits stay protected: the event capture (FR-18) and existing backups hold them, and no expiry applies to them until the recheck has classified them.
- The classification and the evidence for it (reachable ref or merged pull request) are recorded in the run record.

### 4.5 Protection and immutability

**Description:** Backups resist tampering. Nobody — the backup operator, an AWS administrator, the AWS account root user, or an attacker with stolen GitHub or AWS credentials — can delete, change or make unreadable an existing backup or run record before its retention period ends.

#### FR-22: Backups cannot be deleted or changed
No identity can delete or modify a backup, run record or audit trail entry, or remove or weaken its protection, while it is locked.

**Consequences (testable):**
- An attempt by the backup operator's credentials, an administrator, or the AWS account root user to delete, overwrite or shorten the lock of a locked backup fails, and the attempt is recorded.
- The architecture names the lock mechanism and shows that nobody, including the root user, can switch it off.

#### FR-23: Lock follows retention
Every backup is locked for exactly as long as it is kept.

**Consequences (testable):**
- Nobody can delete or change a backup at any point during its retention period.
- Any extension (approved, auto-extension or dependency extension, FR-32) extends the lock together with retention. Kept data is never left unlocked.
- A lock can be extended; no one can shorten it.

#### FR-24: Stolen credentials cannot destroy backups
A stolen GitHub credential or AWS credential, including the backup operator's, is not enough to delete, alter or make unreadable any existing backup.

**Consequences (testable):**
- Strata's GitHub access for backup is read-only, and its restore access reaches only repositories Strata itself created (NFR-S1), so a stolen Strata GitHub credential cannot change existing repositories or backups.
- No single credential can disable, delete or revoke access to the encryption keys protecting backups in a way that makes them unreadable before their retention ends.
- Content written by an attacker with a stolen write credential cannot overwrite or hide existing backups; unexpected storage growth is visible in the daily email (FR-54).

#### FR-25: Backup operator powers are limited
The backup operator can trigger backup runs (but not upload or modify backup data directly, FR-62), trigger retries, perform restores and restore tests, and carry out approved extensions. Apart from these, only Strata's own automatic retention operations change retention: dependency extensions (FR-32), at-risk classification (FR-20) and auto-extensions (FR-31). None of them ever shortens a lock, and each is recorded in the audit trail. Retention changes are applied only by Strata after it checks the recorded approval or rule; the backup operator triggers approved extensions but holds no right to change locks directly.

**Consequences (testable):**
- The backup operator cannot carry out an extension that has no recorded approval (FR-29).
- A restore never changes stored backups.

#### FR-61: Safety settings are protected
Changes to settings that define Strata's safety are recorded and announced.

**Consequences (testable):**
- Covered settings include: schedule and expected end; retry and rate-limit settings; alert recipients and role holders; escalation deadlines; the bulk-deletion threshold (FR-55); the flood threshold (FR-66); the daily-email deadline (FR-49); the watchdog; retention and lock durations.
- Every change is recorded in the audit trail with who and when, and announced to the backup operator, the second failure contact and the budget owner.
- Retention and lock durations can never be set below 1 year for routine snapshots or 3 years for at-risk data.

#### FR-62: Backups and run records cannot be forged
Only Strata's own backup identity writes backup data and run records, and run records are tamper-evident.

**Consequences (testable):**
- The backup operator can trigger a backup run but cannot directly upload or modify backup data or run records.
- Each run record is chained to the previous one so that a missing, altered or inserted record is detectable.
- Run records and backup data are verified before every restore and restore test; a failed check is a backup-failure alert.
- Any write to backup storage outside a recorded backup run or event capture raises a security alert (FR-64).

#### FR-63: Account- and key-level protection
No AWS account-level or key-level action can remove or make unreadable a locked backup before its retention ends.

**Consequences (testable):**
- Any attempt to delete or disable an encryption key protecting backups, to close or detach the AWS account holding them, or to change the account-level guardrails that protect them raises a security alert (FR-64).
- The architecture names the mechanisms and states any remaining risk; the remaining risk is listed in §10.

#### FR-64: Tampering attempts are alerted
Any refused attempt to delete, overwrite or shorten the lock of protected data, any write outside a backup run or event capture, and any action under FR-63 raises a security alert.

**Consequences (testable):**
- Security alerts have a 1-hour acknowledgment deadline and follow the security chain: backup operator → second failure contact → an org owner (FR-47). The chain ends with an org owner because the attempt may use the backup operator's own credential.
- Every security alert is listed in the daily email.

### 4.6 Retention, expiry and extensions

**Description:** Two retention classes keep costs low and alerts rare. Routine snapshots expire on their own after at least 1 year with no one involved. At-risk data is kept 3 years and is never removed without a person deciding; an unanswered warning keeps the data. Retention can be extended but never shortened. Realizes UJ-4.

Retention rationale (from the brief): 1 year covers bugs found long after they were introduced and is above every Glacier minimum storage period, so Orvex never pays for storage it has already deleted. 3 years for at-risk data because investigations take long, the data is gone for good once it expires, and it is rare and small.

#### FR-26: Routine snapshots expire automatically after 1 year
The routine snapshot of a backed-up day is kept and locked for at least 1 year from that day, then expires with no approval. Stored objects that newer backups still need stay locked for as long as they need them (FR-32).

**Consequences (testable):**
- No routine snapshot expires before 1 year from its backed-up day.
- A stored object that a routine snapshot still within retention depends on never expires, even if it was written more than a year ago (FR-32).
- Test: a repository with no changes for 13 months can still be restored as of today and as of every backed-up day in the last year.
- Expiry of a routine snapshot never makes any backed-up day still within retention unrestorable (FR-32).
- Expiry generates no alert.

#### FR-27: At-risk data is kept 3 years and needs a decision to go
At-risk data is kept and locked for 3 years and expires only after an explicit, recorded decision.

**Consequences (testable):**
- At-risk data expires at the end of its current lock only if one of these is recorded: the repo owner decided to let it expire (repo admins or an org owner may decide this only when the repository has no team or the warning has escalated to them), or the budget owner (or the stand-in org owner, FR-30) denied an extension.
- An acknowledgment alone is not a decision. With no decision, the auto-extension applies (FR-31).
- **No automatic deletion path exists for at-risk data without a decision.** It is deleted only after its lock has ended and a recorded decision names it; until then nothing, including Strata's routine expiry, can remove it. A lapsed lock without a decision never leads to deletion.
- The 30-day expiry warning (FR-28) remains the main warning mechanism.
- Each expiry decision is recorded in the audit trail with who and when.

#### FR-28: Expiry warnings
Strata sends an expiry warning to the repo owner 30 days before at-risk data expires.

**Consequences (testable):**
- The warning names the repository, the rewrite event that created the at-risk data, the data's size, its expiry date, the monthly cost of keeping it, and how to request an extension.
- Warnings are alerts with a 24-hour acknowledgment deadline and follow the repo-alert escalation chain (FR-47).
- Warnings repeat 30 days before the end of each extension or auto-extension.
- Pending warnings are listed in the daily email.

#### FR-29: Extension request, approval and execution
A requester can request an extension; the budget owner approves or denies it; the backup operator carries out an approved extension.

Requesters are the repo owner (the team assigned to the repository) first, and repo admins or an org owner as stand-by. The approver is always the budget owner, or an org owner as stand-in budget owner (FR-30).

**Consequences (testable):**
- The requested length is a multiple of the Glacier minimum storage period.
- The request shows the full cost of the extension, including the data it depends on (FR-32).
- The request reaches the budget owner as an alert with a 24-hour acknowledgment deadline. **The 24 hours are an acknowledgment deadline, not a decision deadline**; the budget owner may take longer to evaluate.
- The decision deadline is the end of the at-risk data's current lock.
- The approver is never the requester.
- The backup operator cannot request or approve an extension. If the person who would carry out an extension is its requester or approver, it is not carried out, and the auto-extension (FR-31) keeps the data safe.
- The backup operator carries out the approved extension by triggering it; Strata applies it only after checking the recorded approval, and the backup operator holds no right to change locks directly. Retention and lock move together (FR-23).
- Request, acknowledgment, approval or denial, and execution are each recorded in the audit trail with who and when.

#### FR-30: Budget escalation ends with a decision-maker
If the budget owner does not acknowledge an extension request within 24 hours, it escalates to an org owner, who can approve or deny it as stand-in budget owner.

**Consequences (testable):**
- An org owner who made the request as stand-in repo owner cannot approve it; a different org owner must decide.
- An org owner acting as stand-in budget owner can only approve or deny the extension; they cannot shorten a lock or delete anything.
- If no eligible org owner exists or none responds, no decision is made and the auto-extension applies (FR-31).

#### FR-58: Retention decisions are authenticated
Every retention decision — an extension request, an approval, a denial, or "let it expire" — is verified before it takes effect.

**Consequences (testable):**
- A decision is checked at least as strictly as an acknowledgment (FR-46) and against the ownership snapshot (FR-57); a forged or unverifiable decision has no effect and is recorded.
- A decision is confirmed in a second step by the same person before it is recorded.
- Each decision is announced to the other party (requester or approver) and to the repo owner, and can be revoked by any of them for 7 days. A denial or "let it expire" takes effect only after those 7 days.
- Test: a spoofed "let it expire" email does not cause expiry and is recorded as rejected.

#### FR-31: Auto-extension when no decision is made
If no extension decision has been made 7 days before at-risk data's lock ends, Strata extends its retention and lock by the Glacier minimum storage period (180 days), then verifies the extension.

**Consequences (testable):**
- The auto-extension length is 180 days (the Deep Archive minimum storage period) for every at-risk object, including small objects kept in S3 Standard (NFR-P3).
- Each auto-extension is reported in the daily email and the monthly cost email with its size and cost. The extra storage is never hidden.
- Applying it 7 days early leaves time to detect and fix a failure before the lock lapses.
- A failed or unverified auto-extension raises a backup-failure alert (FR-45). The data is still not deleted (FR-27).
- Test: with the auto-extension job disabled, the data survives the end of its lock and a backup-failure alert fires.
- Auto-extension repeats until a decision is made. It is the only extension of at-risk data Strata applies without an explicit decision.

#### FR-32: Retention respects dependencies
Keeping or extending any backup keeps everything that backup needs to be restored. Dependency extensions are automatic and visible.

**Consequences (testable):**
- Every stored object that a backed-up day depends on stays locked while any newer backup still needs it, and for at least 1 year after the latest backed-up day that needs it. Releasing that protection is recorded in the audit trail, and the storage it keeps is shown in the daily email.
- Because storage is incremental, a backup can depend on data written on earlier days. Extending at-risk data from one day also extends, with its lock, all data that day's restore depends on.
- No expiry or auto-extension ever leaves a backup within retention unrestorable. The restore test (FR-42) checks this.

#### FR-33: Extending is safe; shortening is impossible
Nobody can shorten a retention period or lock, and nobody can delete a backup before its retention ends.

**Consequences (testable):**
- No role, approval or configuration change shortens retention of existing backups.

### 4.7 Restore

**Description:** Restore rebuilds any repository exactly as it was on any backed-up day, into a new repository, without needing GitHub. No approval is needed to restore. Repo owners, repo admins and org owners can initiate a restore; the backup operator performs restores as part of operations. A documented and regularly tested procedure proves it works. Realizes UJ-2, UJ-3, UJ-6.

#### FR-34: Who can initiate a restore
Repo owners and repo admins of a repository, any org owner, and the backup operator can initiate a restore of that repository. No approval is needed: the initiator starts the restore by email and confirms it through a single-use link. The initiator's identity is verified as strictly as a retention decision (FR-58), against the ownership snapshot (FR-57).

**Consequences (testable):**
- For a deleted repository, the repo owners and repo admins are those in its last run record (FR-5).
- When GitHub is unavailable, permissions are checked against the last ownership snapshot (FR-57); the backup operator can always initiate a restore.
- A person who is not one of these roles for the repository cannot initiate its restore.
- The repo owner and the backup operator are told about every restore: who, which repository, which backed-up day, and where it was created.
- Restores per person are rate-limited, and restore cost is shown in the daily email.
- Every restore records who initiated it, which repository, which backed-up day or event capture, and where the result went.

**Notes:** How a non-operator initiates a restore without a UI is an architecture decision (Q5). The behavior above must hold whatever the mechanism.

#### FR-35: Restore into a new repository only
A restore always produces a new repository. It never overwrites, merges into or changes an existing repository.

**Consequences (testable):**
- Every restore first builds a private copy of the restored repository inside Orvex's AWS account. The copy is kept for 30 days and then removed.
- When GitHub is available, Strata then creates the restore destination itself, as a new private repository inside Orvex's GitHub org, and places the restored repository there. The initiator never supplies the destination.
- When GitHub is unavailable or Orvex's GitHub access is lost (FR-38), the private copy in Orvex's AWS account is the restore result; it stays there until it can be placed in the org, within its 30 days.
- A restore whose destination already exists is refused.
- Moving a restored repository out of the org is a separate human action outside Strata. Strata records which repositories are restores, by repository ID, and a transfer of one out of the org, or a change of its visibility to public, raises a security alert (FR-64). It follows the security chain and is also sent to the repo owner.
- Strata cannot detect copies made by cloning; this residual risk is listed in §10.

#### FR-36: Exact restore of a backed-up day
A restore rebuilds a repository as of a chosen backed-up day with exactly the refs and commit IDs in that day's run record, plus the LFS objects and wiki as of that day.

**Consequences (testable):**
- Every branch and tag in the run record exists in the restore and points at the same commit ID; no other refs exist.
- Every LFS object referenced by restored commits is present.
- The wiki matches its state in that day's run record.

#### FR-37: Restore of rewritten history
A repository can be restored as of the state saved by an event capture, and old commits from any rewrite event can be restored.

**Consequences (testable):**
- For a rewrite event, a restore can produce the ref as it was before the event, from the event capture if it succeeded, otherwise from the last backed-up day before the event.

#### FR-38: Restore without GitHub
A restore works when GitHub is unavailable or Orvex's GitHub access is lost or stolen.

**Consequences (testable):**
- Reading backups and building the restored repository need no GitHub credential and no GitHub availability. The private copy in Orvex's AWS account (FR-35) is produced in every case.

#### FR-39: Restore time
A restore finishes within 24 hours of being initiated.

**Consequences (testable):**
- Measured from initiation to a verified restored repository, for the largest repository, including any Glacier retrieval time.
- **Provisional (Q1).** The architecture chose Glacier Deep Archive with Standard retrieval, which takes up to 12 hours (AD-3); the target is finalized once repository sizes are confirmed and rebuild time is measured. A storage class whose worst-case retrieval cannot meet it is not used for data needed for restore.

#### FR-40: Every restore is verified
Every restore verifies its result against the run record and reports pass or fail.

**Consequences (testable):**
- Verification checks every ref name and commit ID, the presence of every referenced LFS object, and the wiki.
- A failed verification is reported to the initiator and raises a backup-failure alert.

#### FR-41: Documented restore procedure
A written runbook describes how to restore one repository as of one date.

**Consequences (testable):**
- An engineer who has not built Strata can restore a repository by following the runbook alone.
- The runbook covers restoring a deleted repository and restoring the commits of a rewrite event.

#### FR-42: Monthly restore test
At least once a month, a restore test restores a repository as of a past backed-up day and verifies it.

**Consequences (testable):**
- Each month's test includes a randomly chosen repository and, at least once a quarter, one of the largest 10% of repositories by size. Empty repositories never count. Each month's test chooses a different repository and backed-up day, and within every 3 months covers: a repository with LFS objects (when any exist), a wiki, a deleted repository or rewrite event (when any exist), and the oldest backed-up day still within retention.
- If no restore test has passed by the 25th of a month, a backup-failure alert is sent by the independent watchdog (FR-15), and repeats until a test passes.
- The restore test runs without a person; the backup operator can also run one at any time.
- A restore test restores into Orvex's AWS account only; it never creates a GitHub repository.
- The result is recorded with date and outcome as restore-test evidence, and appears in the daily email. A failed test raises a backup-failure alert.

#### FR-43: Restore-test evidence is kept
Restore-test results are kept in the audit trail with date, repository, backed-up day, duration and outcome, for as long as the audit trail (FR-52).

### 4.8 Alerts, acknowledgment and escalation

**Description:** Every alert requires acknowledgment; unacknowledged alerts escalate along a chain that always ends with someone who has authority to decide. Email is the only channel in v1. The PRD fixes acknowledgment behavior; the mechanism is an architecture decision (Q4).

#### FR-44: Email only in v1
All alerts, warnings and reports are delivered by email.

**Consequences (testable):**
- No paging, chat or incident tool is required. Adding one later must not need changes to alert classes, deadlines or chains.
- A failure to send any email is recorded and retried; a persistent send failure is shown in the next successfully sent daily email.

#### FR-45: Alert classes and acknowledgment deadlines

| Alert class | Trigger | Acknowledgment deadline | Why |
|---|---|---|---|
| Rewrite event | Force-push, branch deletion that is not routine (FR-55), tag move, tag deletion, repository deletion (FR-17, FR-19) | **1 hour** | Backups are safe, but a live or deployed repository may be broken |
| Security | Tampering attempt, write outside a run or unexplained storage growth, account or key action, rejected-event spike, restored repository moved out of the org or made public (FR-16, FR-35, FR-54, FR-62–FR-64) | **1 hour** | May be an attack using a real credential |
| Ownership change | Team, repo admin or org owner change (FR-57) | **1 hour** | May be the first step of an attack that would silence alerts |
| Backup failure | Failed auto-extension or classification (FR-20, FR-31), event-listener misconfiguration (FR-19), unconfirmed missing repository or change to Strata's GitHub access (FR-60), attempted overlapping run (FR-65), failed run-record verification (FR-62), retries exhausted (FR-12), missed or late run (FR-15), failed restore verification or restore test (FR-40, FR-42) | **1 hour** | Every failure is a protection gap; prevents several days without backup |
| Expiry warning | FR-28 | **24 hours** | Not urgent; sent 30 days before expiry |
| Extension request | FR-29 | **24 hours** (acknowledgment, not decision) | Not urgent; decision may take longer |
| No-owner repository | FR-5 | **24 hours** | Must be fixed before it matters |

#### FR-46: Acknowledgment behavior
A recipient can acknowledge an alert directly from the alert email.

**Consequences (testable):**
- Acknowledging requires no AWS or GitHub login.
- An acknowledgment counts only if it carries a single-use secret sent only to that recipient and is confirmed by a deliberate action; opening or prefetching a link is not enough. Tests cover a link scanner and a forwarded email.
- Only acknowledgments from the alert's current recipients, as given by the ownership snapshot (FR-57), count. A forged acknowledgment, or one produced automatically (for example by an email security scanner), does not stop escalation.
- An acknowledgment stops escalation for that one alert only; it never silences future alerts.
- Security alerts raised by the protected backup account are acknowledged within that account, independent of the account that runs the backups. Alerts that describe an ongoing condition (for example "no completed run") repeat until the condition clears and need no acknowledgment.
- Every acknowledgment (who, when, which alert) and every escalation step is recorded in the audit trail, referenced from the next run record, and shown in the daily email.

#### FR-47: Escalation chains
An alert not acknowledged by its deadline moves to the next recipient in its chain.

| Chain | Steps |
|---|---|
| Repo alerts (rewrite event, ownership change, expiry warning, no-owner repository) | 1. Repo owner (assigned team) → 2. all repo admins → 3. an org owner |
| Backup failure | 1. Backup operator → 2. second failure contact → 3. an org owner, if still unacknowledged 24 hours after the alert was first sent |
| Security | 1. Backup operator → 2. second failure contact → 3. an org owner |
| Budget (extension request) | 1. Budget owner → 2. an org owner other than the requester (FR-30) |

**Consequences (testable):**
- A repository with no team starts the repo-alert chain at step 2.
- The backup operator is not in the repo-alert chain. They receive only Strata-related alerts: backup failures and security alerts (FR-64, including restored repositories moved out of the org, FR-35).
- Repo-alert recipients come from the ownership snapshot (FR-57), not live GitHub data.
- The org owner is the last step of the repo-alert and budget chains and has authority to decide.
- Repo admins are considered unavailable when they do not acknowledge by the deadline; no other availability signal is needed.

#### FR-48: Alerts never stop at the end of a chain
An alert unacknowledged at the last step of its chain keeps repeating until acknowledged.

**Consequences (testable):**
- At the last step of the repo-alert or budget chain, the alert repeats every 24 hours.
- At the last step of the backup-failure chain, the alert repeats every hour to the backup operator, the second failure contact and the org owner.
- Every unacknowledged alert stays listed in the daily email until acknowledged.

#### FR-66: Event floods
A burst of events never buries the event that matters, and every event remains individually recorded.

**Consequences (testable):**
- Above 10 rewrite events in one repository within one hour, Strata sends one flood alert and groups the following notifications for that repository into a digest. The threshold is a protected setting (FR-61).
- Grouping changes notifications only: every event is still recorded individually in the run record and audit trail, still gets its own event capture, and is still listed in the daily email.
- Default-branch deletions, default-branch force-pushes and repository deletions are always notified individually and first.
- Event captures are queued so that they never stop or delay the backup run beyond its expected end (FR-14).

#### FR-67: Recipients can always be reached
Every alert recipient has a defined, verified email address.

**Consequences (testable):**
- Strata maps each GitHub identity to an email address from a defined source (fixed in the architecture).
- A recipient whose address cannot be found, or whose email bounces, is treated as unavailable: the alert escalates immediately and the problem is listed in the daily email under ownership hygiene (SM-11).

#### FR-57: Ownership changes cannot silence alerts
Alert routing, acknowledgments and decisions rely on the ownership snapshot, and ownership changes are themselves alerted.

**Consequences (testable):**
- Rewrite-event alerts, expiry warnings and no-owner-repository alerts go to the repo owners and repo admins in the ownership snapshot, not to owners added since.
- A change of a repository's assigned team or repo admins, or of the org owners, raises a 1-hour alert to the **previous** repo owner (and previous repo admins if there was no team), following the repo-alert chain. It does not go to the backup operator.
- An acknowledgment, extension request, "let it expire" decision or approval from someone who gained the role within the last 7 days does not stop escalation and does not count as a decision.
- On Strata's first-ever backup run there is no earlier snapshot; roles in that first ownership snapshot count as established.
- Test: reassign a repository to a new team, then force-push; the alert reaches the previous team and the new team's acknowledgment does not stop escalation.

### 4.9 Reporting

**Description:** A clear, good-looking daily email tells the backup operator what happened, and a monthly cost email tells the budget owner what Strata costs and how that is changing. Realizes UJ-1.

#### FR-49: Daily email every day
A daily email is sent after every backup run, and also when a run fails or does not happen.

**Consequences (testable):**
- If no backup run completed, the daily email (or the watchdog alert, FR-15) says so; there is no day without a message.
- A missing daily email is itself a Strata failure: the runbook requires the backup operator to investigate when no daily email has arrived by the configured daily-email deadline (a protected setting, FR-61). The second failure contact also receives the daily email, so noticing its absence does not depend on one person.
- A quiet day's email states "0 bytes of new backup data" and that the run record was written.

#### FR-50: Daily email contents
The daily email shows, at minimum:

- **What ran:** run start, end, duration against the expected end; repositories checked; newly discovered repositories; the number of event captures since the last email (one per push), with every failed or partly successful one listed.
- **What changed:** repositories with pushes; refs added, moved or removed.
- **Rewrite events:** every one, with how it was detected and the event capture result.
- **Routine branch deletions:** count per repository, with the evidence (reachable ref or merged pull request).
- **Growth:** new backup data written (Git, LFS, run records), total stored by retention class, and growth against the previous 7 and 30 days.
- **Failures and reliability:** failed repositories, every retry, rate-limit waits, gaps (FR-11), failed email sends.
- **Spend:** cost for the day and month to date, with LFS as a separate line (an estimate where AWS billing data lags).
- **Ownership:** repositories with no owner team.
- **Retention:** pending expiry warnings, extension requests awaiting decision, auto-extensions applied, and storage held by extensions and auto-extensions as its own line, highlighted when it grows.
- **Alerts:** alerts sent, acknowledged, escalated, and still unacknowledged.
- **Restore activity:** restores and restore tests since the last email and their verification result.

**Consequences (testable):**
- The most important status (all good / problems found) is readable in the first lines without scrolling.
- The email renders legibly in the email clients Orvex uses on desktop and mobile; the architecture names them.
- Alerts and emails contain no commit messages, file contents or file paths; they identify repositories, refs and commit IDs only. Email is delivered over TLS.

#### FR-51: Monthly cost email
Each month the budget owner receives a cost email.

**Consequences (testable):**
- It shows: total monthly cost; breakdown by storage (per class and retention class), requests and per-object charges, compute, encryption keys, monitoring and email; LFS as a separate line; the storage and cost kept by approved extensions and by auto-extensions; growth compared with the previous month and the trend over the last 12 months.
- It flags cost growth that exceeds data growth (see SM-6), and flags growth in storage held by extensions, so abuse of the extension permission is caught by cost reporting.

### 4.10 Audit trail

**Description:** Every operation is recorded and visible, so every decision and every action can be traced to a person or to Strata itself.

#### FR-52: Everything is recorded
Strata records every operation and decision in a tamper-resistant audit trail.

**Consequences (testable):**
- Recorded: backup runs and event captures; manual retries; restores and restore tests (who, what, when, result); extension requests, acknowledgments, approvals, denials and executions; auto-extensions; expiries; alerts, acknowledgments and escalations; rejected-event counts (FR-16); failed attempts to delete or change protected data (FR-22).
- Audit trail entries are locked like run records and cannot be changed or deleted by anyone before their retention ends.
- The audit trail is kept for at least as long as the longest-kept data it describes, and at least 3 years. Event and classification records are kept as long as the at-risk data they justify, including through extensions.

#### FR-53: Audit trail is readable
The backup operator can list and filter audit trail entries by repository, time range, operation type and person, without GitHub access.

#### FR-54: Unexpected growth is visible
Storage or cost growth that is not explained by new pushes, LFS or extensions is highlighted in the daily email.

**Consequences (testable):**
- Each run compares stored bytes against the bytes it wrote; any growth not written by a backup run, event capture or extension is highlighted and raises a security alert (FR-64).

## 5. Cross-cutting non-functional requirements

### 5.1 Security

- **NFR-S1 Least privilege on GitHub.** Strata's GitHub access for backup is read-only, org-wide, and limited to what backup needs (repository contents, LFS, wikis, metadata, team and admin membership, events). Restores use a separate identity that can only create new private repositories and reach only the repositories it created (FR-35).
- **NFR-S1a Least privilege on AWS.** Each Strata component has only the AWS permissions it needs. No component that reads GitHub or sends email can delete or change stored backups.
- **NFR-S2 Machine identity.** Strata's GitHub and AWS access belong to Strata, not to a person. No backup run, event capture or restore test depends on an individual's credentials, and staff leaving does not break Strata.
- **NFR-S3 Encryption.** All backups, run records and audit trail entries are encrypted at rest. All data is encrypted in transit between GitHub, Strata and AWS services, and in email links.
- **NFR-S4 Separation of duties.** The powers in §2.1 are enforced by the system, not just by policy: no role can do what its "Cannot" column forbids.
- **NFR-S5 No secrets in source.** No credentials, keys or private Orvex information are stored in Strata's source repository or documentation.
- **NFR-S6 Restored data is sensitive.** Backups contain whatever was ever committed, including secrets committed by mistake. Restored repositories are created by Strata and private: always first as a copy inside Orvex's AWS account (kept 30 days), then, when GitHub is available, as a new repository inside Orvex's GitHub org (FR-35). They are accessible only to the initiator and the roles in FR-34: the AWS copy through a single-use link that issues a 15-minute download link, with every download audited.
- **NFR-S7 Event endpoint.** Anything that receives events from GitHub accepts only authenticated GitHub events and cannot be used to read, change or delete backups.

### 5.2 Reliability

- **NFR-R1 No silent failures.** Every failure — backup, event capture, restore, restore test, email send, missed run — appears in an alert, the daily email or both. Silence never means "all fine".
- **NFR-R2 Nothing lost from completed backups.** Any commit, LFS object or wiki state in a completed backup is restorable for its full retention period.
- **NFR-R3 Independent watchdog.** The component that detects missed runs (FR-15) does not share a single point of failure with the backup run.
- **NFR-R4 Idempotent runs.** Re-running a backup run or event capture never duplicates stored data or corrupts a backup.

### 5.3 Scalability

- **NFR-SC1 No size ceiling.** Today's size (about 93 repositories, about 4 GB of Git data, no LFS) is a starting point, not a limit. The 10× scenario is a planning scenario, not a cap and not a forecast: 40 GB of Git data and 10× the repositories (about 930), branches, tags and daily changes. Strata must keep working beyond it.
- **NFR-SC2 Linear cost.** At 10× today's data, the monthly bill grows no more than 10× (SM-6).
- **NFR-SC3 Run duration.** The architecture states the expected run duration at today's size and in the 10× scenario; the expected end is set from it, and a run that exceeds it is reported (FR-15).
- **NFR-SC4 Very large repositories.** A repository backup still running at the next scheduled start continues and is reported, never duplicated. The restore-time target (FR-39) is re-checked whenever the largest repository doubles in size.

### 5.4 Platform constraints (from the assignment)

- **NFR-P1 AWS only.** Every Strata component is an AWS service. GitHub is only the source.
- **NFR-P2 Serverless first.** Prefer Step Functions, Lambda and similar managed services. A VM is acceptable only if cheaper or simpler, and only on ARM (Graviton).
- **NFR-P3 Glacier for long-term copies.** Long-term backups live in S3 Glacier Deep Archive. Exceptions, all locked exactly like other backups: backup objects smaller than 128 KB stay in S3 Standard, where Glacier's per-object charges would exceed the data cost (COST-7); new full copies of a repository (FR-8) and other backup objects of 128 KB or more stay in S3 Standard until Strata has read and verified them, then move to Deep Archive, and an object still unverified after 24 hours raises an alert; run records and the audit trail are in S3 Standard. The architecture shows why, given minimum storage durations, per-object overhead and retrieval times (AD-3).

## 6. Cost requirements

There is **no fixed budget**. These rules replace one.

- **COST-1 Cheapest design that works.** The cost model compares at least three credible designs that differ in their main compute and storage choices. Each must meet every other requirement in this PRD, with costs shown under stated assumptions. Strata uses the cheapest, and the cost model shows why it beats the others. Tie-break: when designs meet every requirement and the cost difference is small, prefer the simpler design with less custom code and fewer failure points.
- **COST-2 Every assumption stated.** The cost model lists every assumption, including request and per-object charges, minimum storage durations, retrieval, compute, encryption keys, monitoring, email, the event listener and event captures, run records and the audit trail, the expected number of pushes per day (each push triggers an event capture), and the expected number of force-pushes and other rewrite events per day, today and in the 10× scenario.
- **COST-3 Today and at 10×.** The cost model shows the monthly bill today and in the 10× scenario (NFR-SC1): 40 GB of Git data and 10× the repositories, branches, tags and daily changes, so per-object charges, API calls and run record size are scaled too.
- **COST-4 LFS as a separate line.** The cost model shows LFS separately, with at least one realistic scenario (for example a few model files of several gigabytes each, changed regularly), so the design does not fall over if Orvex adopts LFS.
- **COST-5 Quiet day.** A quiet day adds 0 bytes of new backup data; the cost model shows the cost of a quiet day's run record and run, today and at 10×.
- **COST-6 Sensitivity.** The cost model names the assumption that moves the monthly bill most and shows the bill if it is wrong.
- **COST-6a Honest comparison.** Each alternative design is the cheapest credible version of its approach, and the comparison names the assumption under which the ranking would change.
- **COST-6b Over time.** The cost model shows month 1, month 12 and steady state (month 36 and later), today and in the 10× scenario.
- **COST-7 Many small objects.** The design must not store backups as many small objects in Glacier where per-object charges would exceed the data cost.
- **COST-8 Simplest design.** The architecture explains why the chosen design is the simplest that meets every requirement, naming what each alternative adds.

## 7. Non-goals

- Strata is **not** a GitHub replacement or a mirror for day-to-day work. It is a backup.
- Strata does **not** restore into existing repositories, roll back live repositories, or fix GitHub state automatically.
- Strata does **not** prevent force-pushes or deletions on GitHub; it makes them recoverable and visible.
- Strata does **not** capture every intermediate state between backup runs; only event captures narrow that gap, on a best-effort basis.
- Strata does **not** let anyone shorten retention or delete backups early, for cost or any other reason.

What v1 leaves out (a web UI, anything outside the org, issues, pull requests, releases and other GitHub data) is listed once, in §8.2.

## 8. Scope

### 8.1 In scope for v1

- Every repository in the org: all commits, branches, tags, Git LFS objects and wikis.
- Daily backup run, incremental storage, run records.
- Automatic retries, rate-limit handling, missed-run watchdog.
- Rewrite-event listening, per-event alerts, best-effort event capture, daily rewrite detection.
- Immutable, locked storage with two retention classes, expiry warnings, extensions and auto-extension.
- Restore into a new repository, restore verification, runbook, monthly restore test.
- Email alerts with acknowledgment and escalation; daily email; monthly cost email; audit trail.

### 8.2 Out of scope for v1

- **Issues and pull requests** (discussions, reviews): require GitHub API data handling and add complexity and storage. Deferred. This is v1's main accepted risk: if a repository is deleted, its issues and PR discussions are lost.
- **Releases** (notes and attached binaries): add complexity v1 does not need. Deferred.
- Repository settings, branch protection rules, collaborators, webhooks, deploy keys, Actions workflows' secrets, variables, environments, artifacts and caches, GitHub Projects, Discussions, gists.
- Anything outside the org: other orgs' and personal repositories.
- Paging, chat or incident-tool integration (future option; FR-44).
- A web UI or dashboard: Strata is email-only in v1.

### 8.3 Later (beyond v1)

Once v1 has proven reliable and affordable: issues and pull requests, then releases. Each addition is weighed against the same cost rules (§6).

## 9. Success metrics

**Primary**

- **SM-1 Coverage.** 100% of repositories, with all branches and tags, backed up within 24 hours of creation (normally within minutes, via event capture). Measured from run records against the org's repository list. Validates FR-1, FR-2.
- **SM-2 Restore accuracy.** 100% of restores and restore tests have exactly the refs and commit IDs GitHub had on the chosen backed-up day (as verified in that day's run record, FR-2), plus all LFS objects and the wiki. Validates FR-36, FR-40.
- **SM-3 Restore time.** Every restore finishes within 24 hours of initiation (provisional, FR-39). Validates FR-39.
- **SM-4 Restore tested.** At least one passing restore test every calendar month. Validates FR-42.
- **SM-5 Loud failure.** 100% of failed runs alerted when they fail, and 100% of missed or late runs alerted within 1 hour of the expected end; 0 failures discovered that were not alerted. Validates FR-12, FR-15, FR-56, NFR-R1.
- **SM-6 Cost scales linearly.** In the 10× scenario (NFR-SC1), the monthly bill is no more than 10× today's. Validates COST-3, NFR-SC2.
- **SM-7 Quiet day.** A quiet day adds 0 bytes of new backup data. Validates FR-8.
- **SM-8 Rewritten history kept.** 100% of commits held in a completed backup before a rewrite event are restorable after it. Validates FR-20, FR-21, FR-37.

**Secondary**

- **SM-9 Event capture success rate.** Share of rewrite events (other than repository deletions) whose event capture saved all overwritten commits. Reported monthly; no target in v1, used to judge whether best effort is good enough. Validates FR-18.
- **SM-10 Acknowledgment time.** Median and worst acknowledgment time per alert class, and how many alerts reached the last step of their chain, per alert source. If more than 10 rewrite-event alerts a week are acknowledged as harmless (for example force-pushes to feature branches), it is raised as a product question. Validates FR-46–FR-48.
- **SM-11 Ownership hygiene.** Number of repositories without an owner team; target 0. Validates FR-5.

**Counter-metrics (do not optimize)**

- **SM-C1 Alert count.** Do not reduce alerts by suppressing events or by batching them beyond the flood rule (FR-66), under which every event is still recorded individually. Fewer alerts must come from fewer real problems, never from classifying incidents as routine branch deletions. Counterbalances SM-5 and SM-10.
- **SM-C2 Monthly cost.** Do not cut cost by weakening retention, locks, encryption, restore testing or coverage. Counterbalances SM-6.
- **SM-C3 Restore speed.** Do not meet the restore time by skipping verification. Counterbalances SM-3.
- **SM-C4 Retry success.** Do not hide unreliable repositories by retrying silently; every retry is reported. Counterbalances SM-5.

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Commits pushed and overwritten between two backup runs are lost if the event capture fails | Some intra-day work unrecoverable | Event capture (FR-18) with reported result; daily guarantee and its limit stated in §4.4 |
| A repository created and deleted between two backup runs | Repository unrecoverable | Accepted limit of daily cadence; repository deletion alert still sent |
| Missed GitHub events (GitHub does not retry failed deliveries automatically) | Event not alerted live | Daily rewrite detection (FR-19) flags it |
| Branch deletions after merges create frequent alerts and at-risk data | Alert fatigue, extra storage | Routine branch deletions classified separately (FR-55) |
| A deletion misclassified as routine hides an incident | Incident not alerted | Strict FR-55 rule; unknown merge state defaults to rewrite event; routine deletions still listed daily and kept 1 year |
| LFS adoption makes LFS the largest cost | Bill grows quickly; changed LFS files stored in full | Separate LFS cost line (COST-4, FR-51) |
| Glacier retrieval time breaks the 24-hour restore target | SM-3 missed | Storage class choice constrained by FR-39 |
| Encryption key deletion or account-level actions make locked backups unreadable or remove them | Backups lost despite locks | FR-24, FR-63, FR-64; remaining risk to be stated by the architecture (Q3) |
| Email is the only channel; if email sending or the AWS side is down or disabled, no alert can be sent | Silent failure | Accepted remaining risk in v1. A missing daily email is treated as a failure the backup operator investigates (FR-49); a future paging or incident tool would close it |
| Extension permission abused to inflate storage cost | Cost, not data loss | Cost reporting (FR-51, FR-54); separation of duties |
| Strata itself fails quietly | Orvex unprotected | Watchdog (FR-15), daily email every day (FR-49) |
| A restored repository is cloned outside Orvex | Code leaves Orvex undetected | Restores land only in Orvex's org, are private and notified (FR-34, FR-35); cloning cannot be detected — accepted residual risk |

## 11. Dependencies

- GitHub: org-level read access for a machine identity; a separate restore identity that can create new private repositories; event delivery for pushes, repository creation and rewrite events; team and admin membership data.
- AWS accounts owned by Orvex (the architecture uses two accounts in an AWS Organization, Q8); email sending from an Orvex domain.
- Named people for each role (§2.1). Orvex's role holders are not yet assigned.

## 12. Open questions

IDs are stable; answered questions keep their IDs under *Resolved questions*.

### 12.1 Still open

- **Q11 — GitHub org base permission.** *Blocks GitHub restores.* What base permission do members of Orvex's GitHub org have? If it is above "No permission", every member can read a restored private repository, which conflicts with NFR-S6 (restored repositories accessible only to the initiator and the FR-34 roles) (AD-18). Owner: Orvex contact.
- **Q7 — Role holders.** Who holds each role at Orvex (backup operator, second failure contact, budget owner).
- **Q8 — AWS Organization.** Does Orvex already use an AWS Organization? The vault account's protection depends on organization policies; if not, one must be created (AD-5). Owner: Orvex contact.
- **Q9 — GitHub plan and verified domain.** Is Orvex's GitHub org on GitHub Enterprise Cloud with a verified domain? Strata reads alert recipients' email addresses from it; otherwise a mapping file is used (FR-67, AD-19). Owner: Orvex contact.
- **Q10 — Data residency.** Does Orvex have a data-residency requirement (for example UK-only)? The region is configuration, default eu-west-1 (AD-14). Owner: Orvex contact.

### 12.2 Resolved questions

- **Q1 — Restore time.** *Answered by the architecture; the target stays provisional until measured (FR-39).* The 24-hour target stays provisional until repository sizes are confirmed and rebuild time is measured. The architecture's budget: almost every restore waits for a Deep Archive Standard retrieval, which AWS states takes up to 12 hours (not an SLA), so a typical restore takes about 12–13 hours; the operator is alerted at 14 hours, and a build gate requires the largest repository with the longest chain to restore within 18 hours (AD-3, AD-18, FR-39).
- **Q2 — Storage classes and lifecycle rules.** *Answered by the architecture (AD-3, AD-7).* Deep Archive for long-term backups, S3 Standard for objects under 128 KB, records and the audit trail, and larger objects until Strata has verified them (NFR-P3); deletion only by lifecycle rules that cannot remove locked or held data.
- **Q3 — Lock mechanism and key protection.** *Answered by the architecture (AD-5, AD-6, AD-7, AD-23).* S3 Object Lock in compliance mode with event and legal holds, in a separate vault account under organization policies; encryption with no deletable customer key. Remaining risk (the AWS Organization's management account) is stated in AD-5.
- **Q4 — Acknowledgment mechanism.** *Answered by the architecture (AD-12).* Signed single-use links to a confirm page; only a deliberate confirmation counts (FR-46).
- **Q5 — Restore initiation mechanism.** *Answered by the architecture (AD-12, AD-18).* A restore is requested by email to Strata, the sender is checked against the ownership snapshot, and the request is confirmed by a single-use link (FR-34, NFR-S6).
- **Q6 — Event capture feasibility.** *Answered by the architecture (AD-4).* Strata captures every push, so commits are normally stored before a force-push can overwrite them; whether GitHub still serves overwritten commits afterwards is not verified, so that part stays best effort and SM-9 measures it.

## 13. Confirmed assumptions

Confirmed by the product owner on 2026-10-05:

- §2.1 / FR-45 — No-owner-repository alerts go to that repo's admins first.
- FR-3 — A rewrite of wiki history is treated as a rewrite event on the repository.
- FR-5 — If several teams are assigned to a repository, all are repo owners.
- FR-12 — Default retries: 3 attempts with exponential backoff, within the run's window to the expected end.
- FR-44 — Persistent email send failures are shown in the next successfully sent daily email.
- FR-50 — Daily spend may be an estimate where AWS billing data lags.
