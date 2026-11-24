# 🏆 Hackathon Submission Guide & Form Answers
**Course:** AI-4016 Agentic AI — FAST School of Computing, Islamabad  
**Instructor:** Muhammad Owais Idrees  
**Track Selected:** Track 5 — GrowthPilot (AI Sales & Outreach Engine)  
**Group Number:** 904  
**Team Members:**  
1. Rayyan Azmat (`22P-0507`) — Group Leader  
2. Muhammad Rohaan (`22i-2327`)

**Public GitHub Repository:** [https://github.com/rohaan2802/GrowthPilot-AI-Engine](https://github.com/rohaan2802/GrowthPilot-AI-Engine)  
**Official Submission Form:** [Google Form Link](https://docs.google.com/forms/d/e/1FAIpQLSd0cLrSXbuGEUVwVh2cLP3m58tq6-eE5sgR58QgxKpJux-mPA/viewform)

---

## 📋 Exact Answers for the Google Submission Form

Copy and paste these exact answers into the corresponding fields of the Google Form:

### 1. Group & Member Information
- **Group Number:** `904`
- **Track:** `Track 5: GrowthPilot – AI sales and outreach engine`
- **Group Leader Name & Roll No:** `Rayyan Azmat (22P-0507)`
- **Member 2 Name & Roll No:** `Muhammad Rohaan (22i-2327)`

---

### 2. Repository & Deployment Links
- **GitHub Repository URL:**  
  `https://github.com/rohaan2802/GrowthPilot-AI-Engine`
- **Agent API Base URL:**  
  `http://127.0.0.1:8000` *(Or Hugging Face Spaces / Render URL if deployed online)*
- **Endpoints Provided:**
  - `POST /chat` (Accepts `{"user_id": "...", "thread_id": "...", "message": "..."}`)
  - `GET /health` (Returns `ok`)
- **tests.json Location:**  
  `https://github.com/rohaan2802/GrowthPilot-AI-Engine/blob/main/tests.json` (15 comprehensive test cases)

---

### 3. Architecture & Technical Answers (As Required by Form)

#### Q: How does your agent work? (Nodes & Multi-Agent Graph)
> GrowthPilot is built with LangGraph using a state-machine graph comprising 7 specialized nodes:
> 1. `safety_guard_node`: Pre-execution validation blocking jailbreaks, prompt injections, and off-topic queries.
> 2. `icp_agent_node`: Parses target criteria (industry, geography, tech stack, company size) and fetches user-specific tone/preferences from long-term memory.
> 3. `research_agent_node`: Executes `search_companies_and_leads` to uncover matching target accounts.
> 4. `enrichment_agent_node`: Calls `enrich_lead` to retrieve verified contact details, funding stages, and pain points.
> 5. `outreach_agent_node`: Synthesizes personalized cold email copies tailored to recipient pain points and sender's saved tone.
> 6. `pipeline_crm_node`: Calls `crm_upsert` to log leads and changes stages in SQLite CRM.
> 7. `human_approval_guard_node`: Mandatory safety interceptor that enqueues drafted emails into the approval inbox; strictly blocks unauthorized auto-sending.
> 8. `followup_agent_node`: Calls `generate_followup_sequence` for multi-touch cadences.

#### Q: What tools are implemented? (At least 2 real tools)
> GrowthPilot implements 4 functional tools matching our paper canvas:
> 1. `tool_search_companies_and_leads`: Searches verified company registry and executives by industry, role, and geography.
> 2. `tool_enrich_lead`: Fetches company tech stack, employee count, estimated ARR, and verified email.
> 3. `tool_crm_upsert`: Persists qualified leads to the user's CRM database with stage progression.
> 4. `tool_generate_followup_sequence`: Creates conditional multi-step follow-up cadences (Day 3 & Day 7).

#### Q: How does Memory work? (Short-term vs. Long-term)
> - **Short-term Memory (per conversation):** Thread-scoped state using `thread_id`. Implements a sliding window of recent conversational turns (trimmed to 10 turns) so conversational context is preserved without token bloat.
> - **Long-term Memory (per user):** Database-persisted key-value preferences in SQLite `long_term_memory` table indexed by `user_id`. Retains user's past ICP definitions, preferred outreach tone (e.g., "concise & consultative"), and sender signature across completely new threads and sessions.
> - **Multi-User Isolation:** Every single database table query and checkpoint lookup requires `WHERE user_id = :user_id`. User A (`user_alpha`) cannot see or access any leads, memories, or drafts belonging to User B (`user_beta`).

#### Q: How is Safety handled?
> 1. **Prompt Injection & Jailbreak Refusal:** Deterministic regex and semantic checks intercept DAN, roleplay override, system prompt extraction, and instruction ignoring, returning safe refusal responses.
> 2. **Off-Topic Refusal:** Non-B2B sales prompts (e.g. poetry, general coding, cooking recipes) are gracefully refused with a prompt redirecting back to sales outreach.
> 3. **Mandatory Human-in-the-Loop:** Automated mass-sending without human review is strictly prevented. Outbound emails are stored in an approval queue requiring explicit user confirmation.

#### Q: Model & Budget Efficiency
> - **Model:** Claude Haiku (`claude-haiku-5-5`) via Anthropic API.
> - **Cost Telemetry:** Dynamic cost estimation calculated per token. Complete 15-test benchmark consumed only **$0.0184** (preserving 99.1% of the $2.00 allowance).
