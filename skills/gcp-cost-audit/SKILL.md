---
name: gcp-cost-audit
description: Read-only audit of one app's GCP resources: which lack the owner, team, purpose and app labels, what the app spends, and the gcloud commands that fill the gaps (printed, never run). Use when asked to "audit GCP labels", "check GCP cost", "what does this app spend", "is everything labelled", or before a budget review of a GCP project.
---

# gcp-cost-audit

**In one line:** Finds the GCP resources of one app that lack the deploy labels, shows what the app spends, and prints the fix commands without running them.

The deploy rule in `~/CLAUDE.md` asks every resource to carry the labels `owner`, `team`, `purpose` and `app`. These scripts find the gaps and the spend. They run only gcloud and bq list, describe and query calls, and every gcloud call names `--project`. The method comes from the audit in georgetown-mdi-gates4/twenty issue 815 (2026-11-24).

Scope: one label marks an app's resources, e.g. `app=twenty-bot`. An old value you name as legacy, e.g. `app=twenty-chatbot`, folds into it and shows as `RENAME`. Resources of other apps are out of scope and not reported.

## The three commands

`<skill>` below is the folder that holds this file.

    bash <skill>/audit.sh <project> <region> <app> [legacy-app-values]
    bash <skill>/cost.sh <project> <app> [legacy-app-values]
    bash <skill>/fixes.sh <project> <region> <app> [legacy-app-values]

E.g. for the twenty bot: `bash <skill>/audit.sh mdi-yimingwu-pets us-east1 twenty-bot twenty-chatbot`. Project, region and app are required, and no script has a default for them. Legacy values are optional, comma-separated.

- `audit.sh` lists Cloud Run services and jobs, Scheduler jobs, buckets, Artifact Registry repos, Pub/Sub topics and service accounts. It prints one row per resource in scope, with `ok`, the missing labels, or `RENAME`, and a suggested purpose from the name. Service accounts and Scheduler jobs take no labels, so it reads `key=value` pairs in their description. In scope: the app label matches, or a legacy value, or no app label and the name holds the app's first word (e.g. `twenty`). Exit 0: no gaps. 1: gaps. 2: a gcloud call failed, or an argument is missing or empty.
- `cost.sh` prints spend to date by label `app` when a BigQuery billing export exists (set `BILLING_EXPORT_TABLE=proj.dataset.table`, or it searches the project's datasets). With no export, it prints the budgets that cover the project and warns when a legacy app value is in no budget filter. The budget API holds the limit, not the spend so far. The manual source for spend is console Billing > Reports, filtered by label `app`. Reports and budget alerts lag about a day.
- `fixes.sh` prints one `gcloud ... update` command per gap. A missing owner or team takes the most common value among the app's other resources. A missing purpose comes from the name. Read and correct each value before anyone runs it.

## Traps

- Shared resources hold this app's files but carry another app's label. In mdi-yimingwu-pets, the repo `cloud-run-source-deploy` and the bucket `run-sources-mdi-yimingwu-pets-us-east1` carry `app=kathleen-chatbot` and hold Twenty images. The audit does not list them. Who owns them is the owner's call, so name them in the report.
- Pub/Sub topics `container-analysis-*` are made and labelled by Google (`goog-managed-by`). The audit skips them.
- A budget filters on one app value. Spend under a second value falls outside it, e.g. `app=twenty-chatbot` Vertex calls ($3.56 by 2026-11-24) fell outside the budget `twenty-bot-50`. `cost.sh` warns about it. Find the code that still sends the old label.
- A gcloud error exits 2 and prints no table. Never read a failed run as "no resources".
- Purpose suggestions come from names only. They are a first draft, e.g. `friday-run` where the owner may want `friday-dump-run`.

## Applying fixes

The scripts never write. Put the printed commands in the report and stop. A command runs only after the owner says run or yes for that exact change.

## Self-test

    bash <skill>/test-audit.sh

CI runs it through `hooks/gcp-cost-audit-selftest.sh`. It puts a fake gcloud and a fake bq on PATH, with fixtures in the shape of real list output, so nothing reaches Google. It covers: all labelled, one gap with a rename, no legacy values, the region and project in their places, a gcloud error (exit 2), a missing or empty argument (exit 2), no default project, region or app in the code, the budget warnings of cost.sh, no write call reaching gcloud, no write verb outside printed text, ASCII only.
