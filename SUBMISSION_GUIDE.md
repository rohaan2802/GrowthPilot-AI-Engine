# GrowthPilot – Submission Guide & Google Form Answers
AI-4016 Agentic AI · FAST Islamabad · Group 904 · Track: GrowthPilot – Sales and outreach

## Final submission steps
1. **Push + redeploy:** `git push origin main` → Render auto-deploys (or Render dashboard → *Manual Deploy → Deploy latest commit*). Wait until `/health` returns `ok`.
2. **Render env vars:** `ANTHROPIC_API_KEY` (required for LLM answers), `MODEL_NAME=claude-haiku-5-5`, `PORT=8000`, optional `DATABASE_URL` (Neon/Supabase Postgres – keeps memory across restarts).
3. **Check links open:** website, `{base}/health`, `POST {base}/chat`, GitHub repo (public), tests.json, demo video, canvas photo.
4. **Demo video (2–3 min):** follow `DEMO_VIDEO_SCRIPT.md`, upload to YouTube *Unlisted* or Drive *Anyone with the link*.
5. **Canvas photo:** upload `Workshop Project Written Format/WorkShop_Wtitten_Activity.pdf` (or a photo) to Drive → Share → *Anyone with the link: Viewer*.
6. **Google Form** (group leader only, editable until the deadline) – paste the answers below.
7. **Google Classroom:** submit the same links and click *Turn in*.

## Google Form answers
| Field | Answer |
|---|---|
| Group number | 904 |
| Group leader | Mohammad Rohaan |
| Members | Mohammad Rohaan (22I-2327)<br>Rayyan Azmat (22P-0507) |
| Track | GrowthPilot – Sales and outreach |
| Product name | GrowthPilot – AI Sales & Outreach Engine |
| One-line pitch | For B2B SaaS founders and small agencies: finds decision-maker leads, enriches them, drafts personalised outreach and tracks the pipeline with human approval; earns via subscriptions ($49/mo Starter – 150 leads, $129/mo Growth – 500 leads) + $8 per extra qualified lead. |
| Live website URL | https://growthpilot-ai-engine.onrender.com/ |
| Agent API base URL | https://growthpilot-ai-engine.onrender.com  (not /docs) |
| GitHub repo | https://github.com/rohaan2802/GrowthPilot-AI-Engine |
| tests.json | https://github.com/rohaan2802/GrowthPilot-AI-Engine/blob/main/tests.json |
| Demo video | *your YouTube unlisted / Drive link* |
| Canvas photo | *your Drive link (anyone with link)* |
| Hosted on | Render |
| Long-term memory stored in | SQLite / local file (or "Hosted Postgres" if `DATABASE_URL` is set on Render) |

**LangGraph design:** LangGraph StateGraph with 12 nodes: safety_guard (blocks injection, off-topic, secrets, cross-user, auto-send) → load_memory (thread checkpoint + user facts) → router (intent) → research_agent (search + enrich) → outreach_agent (tone-aware draft) → pipeline_agent (CRM upsert + Approval Inbox); crm_agent (view pipeline / move stage / approvals); followup_agent (3-touch cadence); approval_agent (asks confirmation before send/delete); memory_agent (recalls facts and earlier messages); responder (claude-haiku-5-5 for open sales questions, grounded on the user's data); finalize (saves short-term memory + usage).

**Tools:** search_companies_and_leads(industry, company_size, location, limit) → matching companies + decision maker (name, title, email, LinkedIn); enrich_lead(company, domain) → funding, news, tech stack, pain point; draft_outreach(lead, tone) → subject + body < 120 words; crm_upsert(user_id, lead) → lead_id + stage "Needs Approval"; crm_get_pipeline(user_id) → leads by stage; crm_update_stage(user_id, lead, stage) → new stage; generate_followup_sequence(contact, company, pain point) → Day 3/7/14 follow-ups.

**Demo data + examples:** Verified demo directory of 13 B2B companies in 11 segments: cybersecurity (SecureAuth – Marcus Vance), DevOps (CloudScale, CloudMetrics AI), FinTech (FinFlow – Sarah Jenkins), HealthTech (PulseHealth), marketing agencies (Nexus, ScaleReach), e-commerce (ShopNest, Lahore), HR tech (TalentBridge, Karachi), EdTech (LearnLoop, Islamabad), PropTech (Propello, Dubai), logistics (FleetPulse, London), AI (NeuralDesk, Berlin). Examples: "Find me cybersecurity B2B SaaS companies with 20-50 employees" · "Find B2B SaaS in FinTech and draft personalized outreach" · "Find HR tech companies in Karachi" · "Move SecureAuth to Meeting Booked" · "Generate a 3-touch follow-up cadence for the top prospect". Outside the directory it says no verified match instead of showing wrong leads.

**Short-term memory:** Per user_id + thread_id: chat history, active ICP, leads found in the chat, pending action awaiting confirmation. Stored as a checkpoint in the DB. Long chats: last 10 turns go to the LLM, older turns are folded into a rolling summary, so name/ICP still survive after 25+ turns.

**Long-term memory:** Per user_id across all threads: name, company, product, role, outreach tone, target industry/size/region, explicit "remember that…" notes. NOT saved: raw transcripts, blocked prompts, prospects' personal data, API keys/secrets.

**User isolation:** Every DB query is filtered by user_id; thread state key is (user_id, thread_id) so two users with the same thread_id never share history; lead ids are per user and the API refuses to overwrite/approve/move another user's lead (404); prompts asking for other users' data are refused. Covered by automated tests.

**Safety:** Rule-based guard before any tool or LLM call refuses prompt injection, jailbreaks, requests for the system prompt/API keys, cross-user data and spam/phishing; off-topic requests (poems, recipes, sports, maths, general knowledge, code) are refused, and the LLM refuses anything the rules miss. Risky actions: never sends automatically – "send" shows the drafts and needs an explicit "yes, send"; deleting leads/memory also needs confirmation; "send without approval" is refused. No spending actions exist.

**Own benchmark:** tests.json 24/24 pass (includes the original 10+ cases; none fail). pytest 147/147 pass.

**Known limitations:** Leads come from a fixed demo directory (no live web search). Sending is simulated (no email provider; approval marks the lead Contacted). On Render free tier SQLite resets on restart unless DATABASE_URL is set to hosted Postgres; the first request after idle can take ~30-60 s (cold start).

**Declaration:** tick all 5 (own key · claude-haiku-5-5 · no key committed · live until 25 Nov · submitted on Classroom – tick the last one after you actually submit there).
