# Security policy

## Reporting a vulnerability

Please report a vulnerability privately through GitHub's private
vulnerability reporting: open the repository's **Security** tab and choose
**Report a vulnerability**. Do not open a public issue for a security
problem.

## Scope

This repo holds demo code, schemas, truth files, fixtures, and synthetic
corpora. It ships no hosted service. The reviewer UI is a local server
that binds to 127.0.0.1 only. Live runs read API keys and the parser base
URL from the environment (see `.env.example`); the repo never stores one.
CI runs a secret scan over the full git history on every push and pull
request.
