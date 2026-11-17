# Architecture

Boxes marked **AI** contain a machine-learning model. AI never decides and never writes to a family: risk
comes from the exact engine, who is told is the family's choice, and a genetic counsellor approves every
invitation. Back to the [README](../README.md).

## Components

```mermaid
flowchart LR
  subgraph Browser
    W["Web app<br/>Next.js 16, React 19<br/>Arabic and English"]
  end
  ID["Identity provider (OIDC)<br/>UAE PASS for families<br/>Entra ID with MFA for staff<br/>built and tested against a mock provider,<br/>not yet against UAE PASS"]
  W <-->|HTTPS, JSON| API["API<br/>FastAPI<br/>security headers, rate limits,<br/>structured logs without personal data"]
  W -.sign-in redirect.-> ID
  API -.verify token.-> ID

  subgraph Deterministic["Deterministic core (no AI)"]
    ENG["Exact Bayesian engine<br/>variable elimination;<br/>every risk number"]
    GATE["Output gate<br/>approved templates and verbatim<br/>MedlinePlus text only"]
    AUD["Hash-chained audit log"]
    GUIDE["Guide (Ask about Silsila)<br/>keyword matcher, 50 fixed answers"]
    FHIR["FHIR R4B<br/>import (checked, then confirmed)<br/>and export"]
  end

  API --> ENG
  API --> GATE
  API --> AUD
  API --> GUIDE
  API <--> FHIR
  API --> DB[("Store<br/>SQLite in the demo<br/>PostgreSQL in production<br/>SILSILA_DATABASE_URL")]
  GATE --> CLIPS["Read-aloud clips<br/>pre-generated, keyed by text hash"]

  subgraph AI["Where AI is used (none of it decides or writes to families)"]
    SPEECH["AI: Azure AI Speech<br/>made the clips offline<br/>from approved text"]
    TRI["AI: triage classifier<br/>character n-gram model<br/>labels only"]
    AOAI["AI: Azure OpenAI<br/>optional, off by default<br/>labels only"]
    VOICE["AI: voice intake<br/>Jais-ASR then Jais 3 draft a tree<br/>counsellor confirms each person"]
  end

  SPEECH -.generated.-> CLIPS
  API --> TRI
  API -.optional.-> AOAI
  TRI --> Q["Counsellor queue<br/>a person reads every message"]
  API --> VOICE
  VOICE -->|"draft tree, after confirmation"| ENG
  classDef ai fill:#fff4d6,stroke:#b07d00,color:#000;
  class SPEECH,TRI,AOAI,VOICE ai;
```

Notes:

- The hosted site replays one recorded voice-intake run; it does not call Jais at request time.
- Read-aloud clips are made ahead of time. A clip is served only when the hash of the text on screen equals
  the hash the clip was made from.
- The output gate re-derives every message from approved content; a message that is not in the approved
  set is blocked and the block is audited.
- The store is SQLite for the one-replica demo and PostgreSQL for several replicas. Production mode refuses
  to start without a PostgreSQL URL, a strong secret and explicit web origins.
- Identity: demo accounts use hashed passwords and signed tokens. The OIDC code is described in
  [`identity-oidc.md`](identity-oidc.md).

## One cascade

```mermaid
sequenceDiagram
  autonumber
  actor Fam as Index person (family)
  actor Cou as Genetic counsellor
  actor Rel as Relative
  participant API as API
  participant Eng as Exact engine
  participant Gate as Output gate
  participant Aud as Audit log

  Cou->>API: Import index result (FHIR R4B) and create the case
  API->>Aud: Record import (or refusal with reason)
  Fam->>API: Enter family tree, including cousin marriages
  API->>Eng: Calculate every relative's carrier chance and each couple's risk
  Eng-->>API: Exact probabilities (or refusal if the tree cannot be right)
  Fam->>API: Give permission; choose who is told and how
  API->>Gate: Build the invitation from approved wording
  Gate-->>API: Approved text only (anything else is blocked)
  API->>Cou: Invitation joins the queue (pregnancies first)
  Cou->>API: Approve the invitation
  API->>Aud: Record approval
  API->>Rel: Private link (names no person and no condition unless chosen)
  Rel->>API: Read sourced information, comprehension check
  Rel->>API: Book counselling
  Cou->>API: Record the test result
  API->>Eng: Update the family's probabilities
  Cou->>API: Close the case with evidence
  API->>Aud: Record closure
```

Declining at step 5 ends the process and is recorded. Nothing is sent before step 8.
