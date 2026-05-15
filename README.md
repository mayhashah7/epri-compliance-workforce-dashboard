# Regulation, Compliance & Workforce

> EPRI AI for Power Challenge — agentic dashboard built on Azure AI Foundry.

Knowledge retrieval, regulatory automation, training, and field-crew intelligence for utility operations

## Architecture

- **Backend**: FastAPI + WebSocket + synthetic data simulator
- **Frontend**: React / Vite / Tailwind / MapLibre / Recharts
- **Agents**: 11 agents registered in **Azure AI Foundry**
  (orchestrator + 10 specialists)
- **Models**: GPT-5 family per-agent (gpt-5 / gpt-5-mini / gpt-5-chat)
- **Deployment**: Azure Container Apps, Bicep IaC

## Agent fabric

| Agent | Domain | Mission |
|---|---|---|
| `cwm-orchestrator` | routing | Routes requests + aggregates evidence |
| `cwm-compliance-doc-retrieval` | regdocs | Conversational search over standards / regs / audits |
| `cwm-violation-report-creation` | violations | Auto-drafted NERC violation self-reports |
| `cwm-outage-regulatory-reporting` | outage_reg | PUC / state-commission outage reports |
| `cwm-codes-standards-interpretation` | codes | Utility-specific code interpretation w/ precedent |
| `cwm-virtual-training-assistant` | training | Just-in-time procedural guidance for field crews |
| `cwm-engineering-knowledge-retrieval` | engineering | Semantic search across engineering knowledge corpus |
| `cwm-training-course-creation` | course | Auto-generated training modules from manuals |
| `cwm-field-experience-synthesis` | field_xp | Cross-crew operational lessons-learned synthesis |
| `cwm-safety-report-analysis` | safety | Near-miss + incident pattern detection |
| `cwm-post-storm-crew-deployment` | deployment | Optimal post-storm crew + materials routing |

## Scenarios

- **NERC CIP Question** → `cwm-compliance-doc-retrieval` — What does CIP-013-2 say about supply-chain risk?
- **Self-Report Draft** → `cwm-violation-report-creation` — Draft a self-report for the PRC-005 missed maintenance
- **PUC Outage Report** → `cwm-outage-regulatory-reporting` — Generate the May major-event-day filing for PUC
- **Code Conflict** → `cwm-codes-standards-interpretation` — Reconcile NESC vs IEEE 516 on hot-stick clearance
- **Crew Q&A** → `cwm-virtual-training-assistant` — How do I isolate a faulted feeder during back-feed conditions?
- **Build Training Course** → `cwm-training-course-creation` — Build a 4-hour course on URD splicing from manual M-118
- **Safety Pattern** → `cwm-safety-report-analysis` — Find recurring near-miss patterns in last 90 days
- **Storm Deployment Plan** → `cwm-post-storm-crew-deployment` — Plan crew deployment for 380 outages across 14 districts

## Local dev

```bash
# API
cd apps/dashboard-api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Web
cd apps/dashboard-web
npm install && npm run dev
```

## Deploy

```bash
./scripts/deploy.sh   # provisions Container Apps + seeds Foundry agents
```

---
Part of the [EPRI AI for Power Challenge 2026](https://epri.brightidea.com/AIforPower2026) demo set.
