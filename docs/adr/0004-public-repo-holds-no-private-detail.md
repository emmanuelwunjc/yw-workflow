# This public repo holds no detail of a private repo

Date: 2026-11-15

The owner decided that this public repo holds no issue numbers or other
details of a private repo, e.g. the repo whose sync code became the general
goal tracker (#146). So before the first push of a branch here, check every
commit on it, and not only the tip, for private detail. A push makes the
detail public, and a rewrite of history cannot take it back: GitHub keeps
`refs/pull/*` heads that anyone can fetch.

## Considered Options

- Push work as usual and scrub later: rejected, because a scrub on GitHub
  means a new repo. On 2026-09-04 a rewrite and a force-push left a removed
  name fetchable from `refs/pull/1/head`, and the fix was a fresh repo.

## Consequences

Work that started with private detail is rebuilt clean on a new branch
before its first push. The old local branches stay local until someone
deletes them (#278).
