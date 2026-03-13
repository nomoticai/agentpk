# Why agentpk

## The problem

When someone says "I'll send you the agent," what do they actually send?

A GitHub repo link. A zip file with a README. A Notion doc with setup
instructions. A Slack message with three dependencies and a prayer.

There is no standard unit for delivering an AI agent. Not between teams.
Not between companies. Not between environments. Every handoff is
improvised, every deployment is someone reading someone else's code and
hoping they understood it correctly.

This is fine when agents are simple scripts that run in one environment
and nobody else ever touches them. That era is ending.

Agents are being built by consulting firms and delivered to clients.
They are crossing between development, staging, and production. They are
being reviewed by security teams who need to understand what they do
before approving them. They are accumulating in shared directories where
nobody has a clear picture of what is running.

The problem is not that agents are hard to build. The problem is that
once built, there is no standard way to package, inspect, and deliver
them — and no way for a receiver to know what they're getting.

---

## What an agent actually needs to travel

An agent that crosses any boundary — between teams, companies, or
environments — needs four things to be useful on the other side:

**A declaration of intent.** What does this agent do? What tools does it
use? What permissions does it need? What data does it touch? Right now
this lives in a README if you're lucky, in someone's head if you're not.

**A runtime specification.** What language? What version? What
dependencies? What is the entry point? This information is usually
scattered across multiple files with no single authoritative source.

**A tamper-evident seal.** Did this file arrive unchanged from the person
who built it? Was anything modified in transit or after delivery?
Currently there is no way to verify this without manual comparison.

**A record of what was verified.** Was the manifest written by a human
from memory, or was it generated and verified against the actual code?
Was the code analyzed to confirm the manifest is accurate? Nobody knows.

The `.agent` format packages all four into a single portable file.

---

## Use case 1: Security review

A vendor builds an AI agent that will run inside your infrastructure.
Before your security team approves it, they need to understand what it
does.

Today, that means getting a GitHub repository link and reading code.
An analyst with Python knowledge spends hours working through the
codebase, building a mental model of what the agent does, what external
systems it connects to, and what data it accesses. Then they write a
summary. Then the vendor says "actually we updated it last week" and the
process starts again.

With agentpk, the vendor delivers `fraud-detection-1.2.0.agent`. Your
security team runs:

```bash
agent inspect fraud-detection-1.2.0.agent
```

In seconds they see the agent's declared capabilities, what tools it
uses and with what scope, what data classes it accesses, what
environments it is permitted to run in, and what its execution model is.

If the package was built with analysis enabled, they also see the trust
score — a machine-computed measure of how well the manifest matches what
the code actually does. Static analysis, LLM semantic review, and runtime
sandbox observations are all recorded in the package. A score of 85 with
no discrepancies tells a different story than a score of 40 with three
undeclared capabilities.

The vendor does not need to provide repository access. The security team
does not need to read source code to begin their review. The `.agent`
file is the review artifact — inspectable, storable, and permanently
tied to the version that was approved.

When the vendor ships version 1.3.0, your team runs:

```bash
agent diff fraud-detection-1.2.0.agent fraud-detection-1.3.0.agent
```

And sees exactly what changed between the version they approved and the
new one. No re-reading code required.

---

## Use case 2: Consulting delivery

A firm builds an agent for a client. At project completion, they need to
deliver it.

The current options are not great. Hand over the repository and explain
the setup. Zip the files and write a deployment guide. Schedule a
handoff call to walk through everything. None of these are clean
deliverables and all of them require the client's technical team to
reconstruct the agent from documentation.

With agentpk, the deliverable is a single file:

```
fraud-detection-1.2.0.agent
```

The manifest inside it declares what the agent does, what it needs, and
how to run it. The checksum ensures the file is exactly what was built
and signed off on. The analysis block records what verification was
performed before delivery.

The client does not need repository access. There is no setup
documentation to follow or misinterpret. The `.agent` file is the
contract of delivery — named, versioned, and self-describing.

Internally, the consulting firm maintains a library of the agents they
have built and delivered. They can run `agent list ./delivered/` and see
every agent, its version, its execution type, and when it was packaged.
Version control for agent deliverables, no additional tooling required.

---

## Use case 3: Internal governance

Once more than a handful of agents exist inside an organization, the
question "what agents are running and what do they do" becomes
surprisingly hard to answer.

Agents accumulate. Teams build them independently. Documentation falls
out of date. The person who built the original agent has moved to another
team. Nobody has a current, accurate picture of what is deployed.

With agentpk, an internal registry is a directory of `.agent` files:

```bash
agent list ./agents/
```

```
Name                     Version   Execution   Tools   Packaged
invoice-processor        2.1.0     scheduled   3       2026-03-01
fraud-detection          0.3.0     triggered   3       2026-02-15
customer-onboarding      1.0.0     on-demand   2       2026-01-30
data-pipeline            0.2.0     scheduled   1       2026-01-20

4 agents found.
```

Each entry links to a self-describing package. Any agent can be
inspected, validated, or diffed against a previous version at any time.
When audit season arrives, the manifest is the record. When a new team
member needs to understand what an agent does, `agent inspect` is faster
than reading code.

This is not a monitoring platform. It is not a deployment system. It is
the minimum viable governance layer for a team that needs to know what
they have built and be able to verify it on demand.

---

## What agentpk does not do

It is worth being direct about this.

**agentpk does not guarantee the manifest is truthful.** A developer can
write `scope: read` in a manifest and put write operations in the code.
The analysis system detects and flags discrepancies, but it does not
prevent a determined bad actor from lying. The trust score quantifies
confidence, it does not provide certainty.

**agentpk does not execute or deploy agents.** It packages them and
provides tools to inspect and verify them. Running them in production,
monitoring their behavior at runtime, and enforcing governance during
execution are separate problems. `agent run` handles simple test
execution. Production runtime governance requires additional tooling.

**agentpk does not control what an agent can do at runtime.** If a
packaged agent has undeclared capabilities and nobody catches it during
review, those capabilities will execute. The `.agent` format creates
accountability for what was declared. It does not prevent execution of
what was not.

Understanding these limits is part of using the tool correctly.

---

## The baseline guarantee

What agentpk does guarantee, on every package, without configuration:

Every `.agent` file contains a SHA-256 hash of every file in the package,
a hash of the manifest, and a hash of the file collection as a whole.
If any file is modified after packing — any byte in any file — validation
will catch it.

```bash
agent validate fraud-detection-1.2.0.agent
```

This tells you the package is intact. It does not tell you the manifest
is honest. That is what the trust score is for.

The combination of tamper-evident packaging and machine-verified trust
scoring is the foundation. Runtime behavioral governance — enforcing that
agents only do what they declared — is built on top of it.

That is a longer story. This document covers the packaging layer.

---

## Getting started

```bash
pip install agentpk
```

Package your first agent:

```bash
agent init my-agent
agent pack my-agent/
```

Inspect a package you received:

```bash
agent inspect received-agent-1.0.0.agent
agent validate received-agent-1.0.0.agent
```

See the [README](README.md) for the full command reference and the
[examples](examples/) directory for working agent projects.
