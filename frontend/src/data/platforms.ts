export type PlatformId = 'linkedin' | 'xthread' | 'medium';

export type HookOption = {
  id: string;
  style: string;
  headline: string;
  description: string;
};

export type Platform = {
  id: PlatformId;
  label: string;
  hooks: HookOption[];
  checklist: string[];
  mermaidCode: string;
  metaPrompt: string;
};

export const platforms: Record<PlatformId, Platform> = {
  linkedin: {
    id: 'linkedin',
    label: 'LinkedIn',
    hooks: [
      {
        id: 'li-1',
        style: 'The Metric/Failure Hook',
        headline: '99% of AI agents crash in production — here is how we fixed state corruption.',
        description: 'Lead with a stark statistic and a vulnerability. LinkedIn rewards evidence-based authority and vulnerability.',
      },
      {
        id: 'li-2',
        style: 'The Contrarian Angle',
        headline: 'Stop building stateless agents. Stateful graph orchestration is the only pattern that survives production.',
        description: 'Challenge the consensus. Contrarian takes drive comment velocity and polarize your audience on LinkedIn.',
      },
      {
        id: 'li-3',
        style: 'The System Design Blueprint',
        headline: 'A production-grade LangGraph runtime: supervisor handoffs, circuit breakers, and Supabase checkpointing.',
        description: 'Position as a reference architecture. Blueprint posts get saved, reshared, and bookmarked by engineering leaders.',
      },
    ],
    checklist: [
      'Format as 5-slide PDF carousel with a strong cover slide',
      'No external links in body text — link in comments only',
      'Include 3 technical tags (#LangGraph #AIEngineering #StateMachines)',
      'Open with the hook line in the first 2 lines before "See more"',
      'End with a question to drive comment engagement',
      'Post Tuesday–Thursday 8–10 AM local time',
    ],
    mermaidCode: `graph TD
    A[Supervisor Agent] --> B{Circuit Breaker}
    B -->|Healthy| C[Worker Node 1]
    B -->|Degraded| D[Worker Node 2]
    B -->|Failed| E[Fallback Agent]
    C --> F[(Supabase Checkpoint)]
    D --> F
    E --> F
    F --> G{State Validator}
    G -->|Pass| H[Publish Output]
    G -->|Retry| A
    G -->|Human Review| I[Human-in-Loop]
    I --> A`,
    metaPrompt: `You are Claude 3.5 Sonnet, acting as a senior content strategist for LinkedIn.

## SYSTEM CONTEXT
You are generating a LinkedIn carousel post about LangGraph state machine
resilience for a technical founder audience (AI engineers, ML architects,
and engineering leaders). The recording analyzed was a system design
walkthrough of a production LangGraph runtime using supervisor-worker
handoffs, circuit breakers, and Supabase-backed checkpointing.

## TARGET AUDIENCE
- AI/ML engineers building agentic workflows in production
- Technical founders scaling AI infrastructure
- Engineering managers evaluating orchestration frameworks

## CORE HOOK
"99% of AI agents crash in production — here is how we fixed state corruption."

## INSTRUCTIONS
1. Draft a 5-slide LinkedIn carousel (cover + 4 content slides).
2. Slide 1: The hook headline + a one-line tease about the failure mode.
3. Slides 2–3: Break down the state corruption problem — lost context,
   race conditions in parallel node execution, and silent data loss.
4. Slide 4: The fix — supervisor handoffs, circuit breakers, and
   Supabase checkpointing with automatic state recovery.
5. Slide 5: A closing question to drive comments.
6. Keep each slide to 40 words max. Use plain, confident language.
7. Do NOT include external links in the body.
8. Suggest 3 technical hashtags at the end.

## FORMAT
Output each slide as:
--- Slide N ---
[Title]
[Body]`,
  },
  xthread: {
    id: 'xthread',
    label: 'X Thread',
    hooks: [
      {
        id: 'x-1',
        style: 'The Metric/Failure Hook',
        headline: '99% of AI agents crash in production. We killed ours 10,000 times to fix that. 5 tweets on supervisor-worker handoffs.',
        description: 'Short, punchy, curiosity-driven. X rewards threads that promise a concrete payoff in the first tweet.',
      },
      {
        id: 'x-2',
        style: 'The Contrarian Angle',
        headline: 'Stateless agents are a toy. If your orchestration isn\'t a stateful graph with circuit breakers, it will fail in prod.',
        description: 'Bold claims travel on X. Back it up with the thread or risk backlash.',
      },
      {
        id: 'x-3',
        style: 'The System Design Blueprint',
        headline: 'How we built a LangGraph runtime with supervisor handoffs, circuit breakers, and Supabase checkpoints — in production.',
        description: 'Technical threads get bookmarked. Structure beats prose on X.',
      },
    ],
    checklist: [
      'Thread length: 5 tweets for optimal completion rate on this topic',
      'First tweet is the hook — keep it under 200 characters',
      'Each tweet should be self-contained but pull to the next',
      'Use line breaks for readability, not walls of text',
      'Include a diagram or screenshot on tweet 2 for visual anchor',
      'End with a CTA: "Bookmark this for your next agent build"',
      'Post at 9–11 AM or 7–9 PM ET for tech audience',
    ],
    mermaidCode: `graph LR
    A[Supervisor] -->|handoff| B[Worker A]
    A -->|handoff| C[Worker B]
    B --> D{Circuit Breaker}
    C --> D
    D -->|tripped| E[Fallback]
    D -->|ok| F[(Supabase Checkpoint)]
    E --> F
    F --> A`,
    metaPrompt: `You are Claude 3.5 Sonnet, acting as a technical storyteller for X.

## SYSTEM CONTEXT
You are writing a 5-tweet thread about LangGraph state machine resilience
for a technical audience on X (formerly Twitter). The source recording
covered supervisor-worker handoffs, circuit breakers, and Supabase
checkpointing in a production AI agent runtime.

## TARGET AUDIENCE
- AI engineers and builders on X
- Developers evaluating agent orchestration tools
- Technical founders sharing build-in-public content

## CORE HOOK
"99% of AI agents crash in production. We killed ours 10,000 times to
fix that. 5 tweets on supervisor-worker handoffs."

## INSTRUCTIONS
1. Write exactly 5 tweets. Number each tweet (1/5, 2/5, etc.).
2. Tweet 1: The hook — punchy, under 200 characters.
3. Tweet 2: The failure — state corruption during parallel node
   execution and lost context across handoffs.
4. Tweet 3: The fix part 1 — supervisor-worker handoffs with circuit
   breakers that trip on repeated failures.
5. Tweet 4: The fix part 2 — Supabase checkpointing for automatic
   state recovery and replay.
6. Tweet 5: CTA — "Bookmark this for your next agent build."
7. Keep each tweet under 280 characters. Use line breaks for scannability.
8. No hashtags in the body. No external links until the last tweet.

## FORMAT
Output each tweet as:
--- Tweet N/5 ---
[content]`,
  },
  medium: {
    id: 'medium',
    label: 'Medium Article',
    hooks: [
      {
        id: 'm-1',
        style: 'The Metric/Failure Hook',
        headline: '99% of AI Agents Crash in Production: A Deep Dive Into LangGraph StateGraph Resilience vs. Traditional Microservice Retries',
        description: 'Medium titles favor specificity and narrative promise. Numbers + stakes + comparison = clicks.',
      },
      {
        id: 'm-2',
        style: 'The Contrarian Angle',
        headline: 'Why Your Agent Orchestration Is Fragile: Stateful Graphs vs. Stateless Microservice Retries',
        description: 'Medium rewards opinionated long-form. Take a stand and defend it with architecture and code.',
      },
      {
        id: 'm-3',
        style: 'The System Design Blueprint',
        headline: 'A Production Architecture for LangGraph: Supervisor Handoffs, Circuit Breakers, and Supabase Checkpointing',
        description: 'Reference-style articles get Medium distribution and evergreen SEO traffic.',
      },
    ],
    checklist: [
      'Article length: 1,500–2,500 words for optimal read ratio',
      'Title under 65 characters for SEO and email previews',
      'Use a subtitle that expands on the hook without repeating it',
      'Include 2–3 code blocks with syntax highlighting',
      'Add the architecture diagram after the intro section',
      'Section headers every 200–300 words for scannability',
      'Compare LangGraph StateGraph resilience to microservice retry patterns',
      'End with a clear takeaway and a question for responses',
      'Submit to "AI Engineering" or "Better Programming" publication',
    ],
    mermaidCode: `graph TD
    subgraph Traditional Microservice
      T1[Service A] -->|HTTP retry| T2[Service B]
      T2 -->|retry| T3[Service C]
      T3 -->|timeout| T4[Dead Letter Queue]
    end
    subgraph LangGraph StateGraph
      L1[Supervisor] --> L2{Circuit Breaker}
      L2 -->|healthy| L3[Worker Node]
      L2 -->|failed| L4[Fallback Agent]
      L3 --> L5[(Supabase Checkpoint)]
      L4 --> L5
      L5 --> L6{State Validator}
      L6 -->|pass| L7[Output]
      L6 -->|replay| L1
    end`,
    metaPrompt: `You are Claude 3.5 Sonnet, acting as a senior engineering writer for Medium.

## SYSTEM CONTEXT
You are drafting a 2,000-word Medium article comparing LangGraph StateGraph
resilience patterns to traditional microservice retry mechanisms. The source
recording was a system design walkthrough covering supervisor-worker
handoffs, circuit breakers, and Supabase-backed checkpointing.

## TARGET AUDIENCE
- AI/ML engineers building production agent systems
- Software architects evaluating orchestration frameworks
- Technical readers on Medium's AI Engineering publications

## CORE HOOK
"99% of AI Agents Crash in Production: A Deep Dive Into LangGraph StateGraph
Resilience vs. Traditional Microservice Retries"

## INSTRUCTIONS
1. Write a full Medium article (1,500–2,500 words).
2. Structure: Hook intro → The problem with stateless retries →
   LangGraph StateGraph architecture → Supervisor-worker handoffs →
   Circuit breakers → Supabase checkpointing → Code examples →
   Comparison table → Takeaways → Discussion question.
3. Include 2–3 Python code blocks showing:
   a. A traditional microservice retry loop (with exponential backoff)
   b. A LangGraph StateGraph with supervisor handoffs
   c. Supabase checkpoint integration for state recovery
4. Include a comparison section contrasting failure modes:
   - Microservice: retry storms, cascading failures, lost state
   - StateGraph: checkpoint replay, circuit breaker isolation,
     supervisor-driven recovery
5. Use clear section headers (H2) every 200–300 words.
6. Write in a confident, technical, first-person voice.
7. Explain the "why" behind each architectural decision.
8. End with a question to drive Medium responses.
9. Do NOT pad with filler. Every paragraph should teach something.

## FORMAT
# [Title]
## [Subtitle]

## [Section 1]
[content with code blocks where appropriate]

## [Section 2]
...`,
  },
};

export const platformOrder: PlatformId[] = ['linkedin', 'xthread', 'medium'];
