---
title: Synthadoc Jobs and Queue
keywords: [job, jobs, queue, job list, list jobs, job status, job id, failed job, pending job, dead job, ingest queue, background job, running job, completed job, synthadoc jobs]
---

# Synthadoc Jobs and Queue

Synthadoc processes ingest requests asynchronously using a background job queue. Each ingest operation (file, URL, web search, batch) creates one or more jobs. You can monitor and manage them from the CLI.

## Listing Jobs

```bash
synthadoc jobs list
```

Shows all jobs in the queue, sorted by creation time (newest first). Each row displays the job ID (8-char hex), operation, status, and creation date.

## Checking a Specific Job

```bash
synthadoc jobs status JOB_ID
```

Shows detailed information for the given job: operation, status, retry count, creation time, and any error message.

## Job Statuses

| Status | Meaning |
|---|---|
| **pending** | Waiting to be picked up by the worker |
| **running** | Currently being processed |
| **completed** | Finished successfully |
| **failed** | Encountered an error (see the `error` field) |
| **dead** | Exceeded retry limit — requires manual intervention |

## Retrying a Failed Job

Failed jobs are retried automatically up to 3 times with exponential backoff. Dead jobs (exceeded retry limit) can be re-queued by re-running the original `synthadoc ingest` command.

## Cancelling / Clearing Jobs

Jobs cannot be cancelled mid-run. Completed and failed jobs remain in the queue log for audit purposes. The queue is stored in `.synthadoc/queue.db`.

## Viewing Jobs in the Web UI

When running `synthadoc web`, the current job queue is visible by asking: *"What are the current jobs?"* or *"List all jobs"* — Synthadoc will query the live queue and show the results inline.
