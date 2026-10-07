# Strata restore runbook: one repository on one date

How to rebuild one GitHub repository exactly as it was on one backed-up day, how long each step takes, and how to check the result. It follows the architecture in `ARCHITECTURE-SPINE.md` (AD-18 restore flow, AD-16 records, AD-3 storage classes, AD-26 restored repositories) and meets PRD FR-34 to FR-43.

> **Status:** written before Strata is built; updated 2026-10-07. Names of commands, roles, buckets and email addresses follow the architecture's conventions and are fixed during the build; update this runbook when they are.
>
> **Worked example used throughout (illustrative, not real Orvex data):** repository `example-service`, GitHub repository ID `700000001`, restored as of **2026-09-14** (a UTC day).

## 1. Before you start

| You need | Why |
|---|---|
| To be a **repo owner** (member of the team assigned to the repo), a **repo admin**, an **org owner**, or the **backup operator** | Only these roles may start a restore (FR-34). Roles are checked against the ownership snapshot recorded before the request, not live GitHub data (AD-12, FR-57). |
| The repository's name (or GitHub ID) and the date you want, as a UTC day | A "backed-up day" is a UTC day (FR-65). If several repositories have had that name, Strata asks for the ID (FR-59). |
| Access to your Orvex email | Restores are requested and confirmed by email; there is no UI (AD-12). No approval is needed: nobody else has to approve your restore. |

**What you get:**
- a **private copy** of the repository, rebuilt and verified, kept for 30 days in Strata's restore bucket in Orvex's AWS account
- if GitHub is available, a **new private GitHub repository** in Orvex's org

A restore **never** changes an existing repository (FR-35).

## 2. Time budget

Every base moves to Glacier Deep Archive as soon as the notary has verified it (AD-3), so **almost every restore waits for a Deep Archive retrieval**. Plan for about half a day.

| Step | Typical | Notes |
|---|---|---|
| 1. Request and confirm | a few minutes | depends on when you click the link |
| 2. Find the backed-up day and check the records | under 5 minutes | |
| 3. Retrieve archived pieces | **up to 12 hours** (Deep Archive, Standard tier) | 12 h is AWS's stated window, **not an SLA**; only a chain written in the last day may still be all in Standard |
| 4. Rebuild | minutes (largest repo about 1 GB) | longer for very large repos (Fargate) |
| 5. Verify | minutes | |
| 6. Store the private copy in AWS | minutes | |
| 7. Create the GitHub repository, set access, push | minutes | skipped if GitHub is down |
| **Total** | **about 12–13 hours** | inside the **24-hour** target (FR-39, provisional) |

- If a restore is still running at **14 hours**, the backup operator is alerted and checks the retrievals (section 7).
- **Build gate:** before Strata relies on this budget, an end-to-end restore of the largest repository with the longest chain must finish within **18 hours**.
- Bulk retrieval (up to 48 hours) is **never** used, because it would miss the target (AD-3).

## 3. Normal restore (automated)

### Step 1: Request and confirm (requester)

1. Send an email from your Orvex address to Strata's restore address (set at build time, for example `restore@strata.<orvex-domain>`). Put this in the subject line:

   ```text
   restore example-service 2026-09-14
   ```

2. Strata checks:
   - that the sender passes the email checks
   - that you hold one of the roles above for `example-service`, using the email addresses recorded in the ownership snapshot (so this works while GitHub is down)
   - that the name is unambiguous. If several repositories have had the name `example-service`, Strata replies with the candidates (repository ID, names, dates) and you send the request again with the ID, for example `restore 700000001 2026-09-14`.
3. Strata replies with a **single-use confirmation link**. Open it and **press the confirm button**; opening the link alone does nothing (AD-12).
4. You receive an acknowledgment with a **restore ID**. The repo owner and the backup operator are also told: who asked, which repository, which day.

If you are not allowed, or the date is outside retention (routine data is kept 1 year; at-risk data 3 years), Strata replies with the reason and nothing else happens.

### Step 2: Find the backed-up day (automatic)

The restore workflow reads **records**, never bucket listings (AD-16):

1. **Restore entry for the repository and day:** the notary's index entry for (`700000001`, `2026-09-14`). The notary writes it as each daily capture of the repository is verified, so it exists even if the run as a whole failed that day. It names the repository-state record and its version ID.
2. **Repository-state record:** `records/repo-state/700000001/{seq}.json`, read by that version ID. This is the exact list of what that day needs:
   - every branch and tag, with commit IDs (and tag object IDs)
   - the wiki state
   - the **object key and version ID** of the chain's base, of each addition in order, and of every LFS object
3. **Retention check:** every object the day needs must still exist with a retain-until more than 24 hours away, so nothing expires mid-restore.
4. **Hash-chain check (step 2b):** for every record used, the workflow walks forward from the nearest monthly checkpoint at or before it and checks that each record's previous-record hash matches (AD-16). A break raises a backup-failure alert, and the restore continues but is marked **untrusted** in the evidence and in every notification.

The day's run pointer, `records/runs/2026-09-14/last-successful.json`, is for reporting: it names the day's last successful run record, or says the day had no successful run. A restore does not need it.

If the repository has no verified daily capture for 2026-09-14, or the day fails the retention check, Strata says so and offers the nearest earlier restorable day.

### Step 3: Retrieve archived pieces (automatic)

1. Pieces stored in S3 Standard are read directly: additions and LFS objects under 128 KB, and any piece the notary has not yet verified (normally only pieces written in the last day).
2. Pieces in Glacier Deep Archive get a retrieval request on the **Standard tier**: up to **12 hours**, $0.02 per GB plus $0.11 per 1,000 requests. The temporary copy expires after a few days.
3. The workflow waits until every piece is available. If any retrieval fails, it raises a backup-failure alert. If the restore is still running at 14 hours, the backup operator is alerted.

### Step 4: Rebuild (automatic, Lambda; Fargate for very large repositories)

The equivalent git steps:

```bash
git init --bare example-service.git
cd example-service.git
git bundle verify base-<sha256>.bundle                   # must pass
git fetch base-<sha256>.bundle 'refs/*:refs/*'
for add in add-<sha256-1>.bundle add-<sha256-2>.bundle ...; do   # strict order from the record
  git bundle verify "$add"
  git fetch "$add" 'refs/*:refs/*'
done
# make refs match the record exactly: set every listed branch/tag, delete any ref not listed
#   (including refs/strata/rescued/* unless this is a rewrite restore, see 5.1)
# put every listed LFS object into lfs/objects/<oid[0:2]>/<oid[2:4]>/<oid>
# rebuild the wiki the same way from its own chain into example-service.wiki.git
```

### Step 5: Verify (automatic)

The restore passes only if **all** of these hold (FR-36, FR-40):

| Check | How |
|---|---|
| Same branches and tags, nothing extra | `git for-each-ref` equals the record's list exactly |
| Same commit IDs (and tag object IDs) | each ref's value equals the record |
| Repository is complete and uncorrupted | `git fsck --full` reports no errors |
| Every LFS object present | every LFS pointer in the restored commits has its object, with matching SHA-256; an object the record marks "unavailable at source" (GitHub never served it) is exempt and listed in the result |
| Wiki matches | the wiki's refs equal the record's wiki state |

On failure, Strata raises a backup-failure alert and tells the requester. Nothing is pushed anywhere.

### Step 6: Store the private copy in AWS (automatic)

The verified repository (and wiki) is written to the **restore bucket** in the worker account as a private copy, kept **30 days** (AD-18). If step 7 is still waiting for GitHub, the expiry is extended and the backup operator is alerted before it lapses. The restore email carries a single-use link that issues a 15-minute download link to the copy. Every download is recorded in the audit trail, and the bucket has CloudTrail data events. This step means a restore still works when GitHub is down (FR-38).

The restored repository is itself backed up from then on, like any other repository (AD-26).

### Step 7: Create the GitHub repository (automatic, if GitHub is available)

1. The **restore-only GitHub App** creates a new **private** repository in Orvex's org **with no team access**, for example `restore-example-service-2026-09-14-<short restore ID>`. A long name is shortened to fit GitHub's 100-character limit, always keeping the restore ID.
2. It grants access only to the initiator and the FR-34 roles for `example-service` taken from the **ownership snapshot**, not live GitHub data.
3. It pushes all branches, tags, LFS objects and the wiki.
4. It reads back the repository's **effective collaborator list** (which includes access from the org's base permission). Only if the list matches does anyone get told the repository is ready; a mismatch is a security alert.
5. The App can reach only repositories it created, never existing ones (AD-10).
6. Moving the restored repository out of the org, or making it public, raises a security alert (FR-35).
7. **When you are done with it, you may delete the restored repository.** If you did no new work in it, the deletion is routine: no alert and no 3-year hold, because Strata recognizes it by its repository ID in the restore evidence and everything in it is already in the source repository's backups (AD-26). If you committed new work to it, back that work up elsewhere first; deleting it is then treated like any other repository deletion (rewrite alert, at-risk data).

### Step 8: Evidence (automatic)

Strata writes restore evidence through the notary: who, which repository, which day, the restore destination's repository ID, every check result (including the hash-chain check and the collaborator check), and the duration. It then emails the requester, the repo owner and the backup operator, with where to find the result. An untrusted restore says so in the evidence and the email.

## 4. Manual fallback (backup operator, when the automation is broken)

Use this only if the restore workflow itself is failing. The operator assumes the **restore-read role** (read-only on the vault, `GetItem` on the vault index, write on the restore bucket). It cannot delete or change backups (AD-5). Every call is in CloudTrail. **Never list the bucket and never read without `--version-id`.**

```bash
# 1. find the repository's state for the day without listing: the restore entry in the vault index
aws dynamodb get-item --table-name <vault-table> --key '{"pk":{"S":"restore#700000001#2026-09-14"}}'   # names <seq> and <state-vid>
aws s3api get-object --bucket <vault-bucket> --key records/repo-state/700000001/<seq>.json --version-id <state-vid> state.json
# 2. verify the hash chain of each record used: walk forward from the nearest checkpoint at or before it
#    (records/checkpoints/<yyyy>-<mm>.json, version ID from the vault index); each record's previous-record SHA-256
#    must match the record before it. Check that every object's retain-until is more than 24 hours away.
#    A break: raise a backup-failure alert and mark the restore untrusted.
# 3. for each object in state.json (key + versionId):
aws s3api head-object --bucket <vault-bucket> --key <key> --version-id <vid>     # shows StorageClass / Restore status
aws s3api restore-object --bucket <vault-bucket> --key <key> --version-id <vid> \
    --restore-request '{"Days":3,"GlacierJobParameters":{"Tier":"Standard"}}'     # only for DEEP_ARCHIVE objects
# poll head-object until Restore shows ongoing-request="false" (up to 12 h)
aws s3api get-object --bucket <vault-bucket> --key <key> --version-id <vid> <local-file>
# 4. rebuild and verify exactly as in steps 4-5
# 5. upload the verified repository to the restore bucket
aws s3 cp example-service.tar s3://<restore-bucket>/<restore-id>/example-service.tar
```

6. If the GitHub copy is wanted, follow step 7 exactly: no team access, grant only the snapshot roles, check the effective collaborator list.
7. **Still claim restore evidence** through the notary (same contents as step 8, marked "manual") and **email the repo owner** and the requester. A manual restore is never silent.

Always read objects **by version ID** from the record or the vault index. A lifecycle "delete marker" might hide the current listing of a still-locked object (AD-7).

## 5. Variants

### 5.1 The state just before a force-push or deletion

- **Choose the restore point:**
  - the **event capture** for that event, which might include commits pushed earlier the same day, or
  - the last backed-up day before the event
- The event alert and the daily email name both options (FR-37).
- In the request, give the event ID instead of a date:

  ```text
  restore example-service event <event_id>
  ```

- The rebuild keeps `refs/strata/rescued/<event_id>` and exposes it as a branch named `rescued/<event_id>`, so the overwritten commits are visible.
- At-risk data is kept 3 years and protected by a legal hold, so this restore stays possible well after the routine data has expired.

### 5.2 A deleted repository

- Ask by its old name or by its GitHub ID. Strata keeps each repository's name history (FR-59). If the name belonged to several repositories, Strata lists them and asks for the ID.
- Who may restore is taken from the **last ownership snapshot** before deletion (FR-34).
- All of a deleted repository's content is at-risk data, kept 3 years.

### 5.3 GitHub is down, or Orvex's GitHub access is lost

- Steps 1 to 6 work without GitHub; the sender check uses the email addresses recorded in the ownership snapshot.
- If inbound email can't reach Strata, the backup operator can start the restore directly.
- The result waits in the restore bucket; its 30-day expiry is extended while step 7 is pending, and the operator is alerted before it lapses.
- Step 7 runs later once GitHub is available.
- Meanwhile, the requester (or any FR-34 role) gets the AWS copy through the single-use link in the restore email. Pressing its button issues a download link valid for **15 minutes**. Every link issued and every download is recorded in the audit trail (AD-18).

## 6. Monthly restore test

What the monthly restore test covers, the restore-App health check, the evidence kept and the 25th-of-the-month alert are described in [`ARCHITECTURE.md` §2.7](ARCHITECTURE.md#27-restore) (FR-42, FR-43, AD-18). The test runs steps 2 to 6 above and never creates a GitHub repository.

**When a test fails,** the backup operator:

1. opens the evidence to see which check failed
2. re-runs the test once
3. if it fails again, treats it as a backup failure: investigates, and doesn't trust that repository's backups until a restore passes

## 7. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| "Not allowed" reply | You aren't a repo owner, admin or org owner in the ownership snapshot | Ask a repo owner or the backup operator. A role gained in the last 7 days doesn't count (FR-57). |
| "No backed-up day" | That UTC day has no verified daily capture for this repository, or some of its objects are within 24 hours of expiry, or it is outside retention | Choose the nearest earlier day that Strata offers. |
| "Which repository?" reply | Several repositories have had that name | Send the request again with the repository ID from the reply. |
| Waiting many hours | Deep Archive retrieval (AWS states within 12 h; not an SLA) | Normal for almost every restore. The operator is alerted at 14 h: check each retrieval with `head-object --version-id`; re-request any that failed. |
| Restore marked "untrusted" | A record's hash chain did not verify (step 2b) | Backup-failure alert raised. Use the result with care; the operator investigates the records before anyone relies on it. |
| "Collaborator check failed" | The restored repository is reachable by more people than the FR-34 roles, often because of the org's base permission | Security alert raised; nobody is told the repo is ready. An org owner fixes the access, then the operator retries step 7. |
| Verification failed | A missing piece, corruption, or a records mismatch | Backup-failure alert raised automatically. The operator investigates with the manual fallback. |
| GitHub step failed | GitHub unavailable or restore App problem | The copy is safe in the restore bucket for 30 days; the operator retries step 7. |
| Restored repo moved or made public | Someone moved it out of Orvex's control | Security alert to the repo owner and the backup operator. Investigate. |
