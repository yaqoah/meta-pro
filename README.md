# Meta Pro

**Editorial intelligence, autonomously distilled.**

A full-stack AI content strategy agent that transforms raw transcripts or recordings into publish-ready strategy playbooks across multiple platforms. Built with LangGraph, FastAPI, and React/TypeScript.

---

## Overview

Drop in a recording or paste a transcript. Meta Pro's multi-agent system reads the signal, extracts the narrative spine, and returns a complete strategy playbook, including:

- **Platform Strategies**: Tailored content strategies for LinkedIn, X, and Medium
- **Visual Diagrams**: Dark-mode Mermaid.js flowcharts explaining architecture and decisions
- **Meta-Prompts**: Ready-to-use prompts for Claude 3.5 Sonnet

The agent autonomously routes work across specialized workers (strategy agent, visual agent, prompt builder) and streams live progress via Server-Sent Events.

---

## Features

- **Multimodal Input**: Upload audio/video recordings (up to 100MB) or paste text transcripts
- **Strategic Angles**: Recruiter, Technical, Founder, Contrarian - each with pre-filled focus directions
- **Real-time Streaming**: Progress updates via Server-Sent Events as the agent works
- **Cross-Platform Output**: Generate content strategies for LinkedIn, X threads, and Medium
- **Visual Documentation**: Auto-generated Mermaid.js flowcharts for technical explanations
- **Resilience**: Circuit breaker pattern, automatic LLM failover, graceful degradation to placeholders

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Meta Pro System                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Frontend    │    │   Backend    │    │  API Keys    │      │
│  │  (React TS)  │◄──►│  (FastAPI)   │◄──►│  (Mistral)   │      │
│  │              │    │              │    │   (Groq)     │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                  │                               │
│                                  ▼                               │
│                      ┌───────────────────────┐                   │
│                      │   LangGraph Graph     │                   │
│                      │                       │                   │
│                      │  ┌─────────────────┐  │                   │
│                      │  │ Strategy Agent  │  │                   │
│                      │  │  (content pln) │  │                   │
│                      │  └─────────────────┘  │                   │
│                      │  ┌─────────────────┐  │                   │
│                      │  │  Visual Agent   │  │                   │
│                      │  │ (mermaid diag)  │  │                   │
│                      │  └─────────────────┘  │                   │
│                      │  ┌─────────────────┐  │                   │
│                      │  │ Prompt Builder  │  │                   │
│                      │  │ (claude meta-p) │  │                   │
│                      │  └─────────────────┘  │                   │
│                      │                       │                   │
│                      └───────────────────────┘                   │
│                                  │                               │
│                    ┌─────────────┴─────────────┐                   │
│                    ▼                         ▼                   │
│            ┌──────────────┐          ┌──────────────┐              │
│            │  MemorySaver │          │  Supabase    │              │
│            │ (in-memory)  │          │  (Postgres)  │              │
│            └──────────────┘          └──────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
meta-pro/
├── backend/                 # FastAPI backend + LangGraph agent
│   ├── app/
│   │   ├── main.py          # FastAPI app with SSE streaming endpoints
│   │   ├── graph.py         # LangGraph state machine & worker nodes
│   │   ├── schemas.py       # Pydantic models for state & outputs
│   │   ├── config.py        # Environment-based configuration
│   │   ├── resilience.py    # Circuit breaker & LLM failover logic
│   │   └── tools/           # Agent tools (transcription, ingestion)
│   ├── requirements.txt     # Python dependencies
│   ├── docker-compose.yml   # Local Redis for development
│   ├── render.yaml          # Render.com deployment blueprint
│   └── .env.example         # Environment configuration template
│
├── frontend/                # React/TypeScript UI
│   ├── src/
│   │   ├── App.tsx          # Main application component
│   │   ├── components/      # UI components
│   │   ├── hooks/           # Custom React hooks
│   │   ├── services/        # API and adapter services
│   │   └── data/            # Platform data definitions
│   ├── package.json         # npm dependencies
│   ├── vite.config.ts       # Vite bundler config
│   └── vercel.json          # Vercel deployment config
│
└── README.md                # This file
```

---

## Getting Started

### Prerequisites

- **Python 3.11+** (backend)
- **Node.js 18+** (frontend)
- **Mistral API Key** (required for LLM and transcription)
- **Supabase** (optional, for persistent state)

### Quick Start (Development)

```bash
# Clone the repository
git clone <repository-url>
cd meta-pro

# Set up backend
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

Configure environment variables:

```bash
# Copy and edit the environment template
copy .env.example .env  # Windows
cp .env.example .env    # macOS/Linux

# Edit .env and add your MISTRAL_API_KEY
code .env
```

Start the backend development server:

```bash
# Option 1: With venv
uvicorn app.main:app --reload --port 8000

# Option 2: Without venv (if uvicorn is installed globally)
uvicorn app.main:app --reload --port 8000
```

Start the frontend development server:

```bash
cd ../frontend
npm install
npm run dev
```

Open **http://localhost:5173** to view the application.

The backend API will be available at **http://localhost:8000**.

### Production Deployment

#### Frontend (Vercel)

1. Create a Vercel project pointing to the `frontend/` directory
2. Set environment variables in Vercel dashboard:
   - `VITE_API_URL` - Your backend API URL (e.g., `https://api.meta-pro.com`)

The `vercel.json` config enables client-side routing (SPA fallback).

#### Backend (Render)

1. Create a Render.com account
2. New → Blueprint → Select this repository
3. Render will auto-detect `backend/render.yaml`
4. Set secrets in Render dashboard:
   - `DATABASE_URL` - Supabase connection string
   - `MISTRAL_API_KEY` - Your Mistral API key
   - `GROQ_API_KEY` - (Optional) Groq API key for failover
5. Deploy

#### Local Docker Compose

```bash
cd backend
docker compose up redis
uvicorn app.main:app --reload
```

---

## Configuration

### Backend Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development` or `production` | `development` |
| `MISTRAL_API_KEY` | Primary LLM key (required) | - |
| `GROQ_API_KEY` | Fallback LLM key (optional) | - |
| `DATABASE_URL` | Supabase Postgres connection | - |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `MAX_STEPS` | Maximum agent steps per run | `10` |
| `MIN_LLM_INTERVAL_SECONDS` | Rate limiting (seconds) | `15.0` |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `http://localhost:5173,http://localhost:3000` |

See `backend/.env.example` for all configuration options.

---

## API Endpoints

### `POST /api/generate/stream`

Stream a content strategy pipeline execution.

**Form Data:**
- `transcript_text` (string): Raw transcript or text input
- `focus_direction` (string): Strategic focus guidance
- `strategic_angle` (enum): `recruiter`, `technical`, `founder`, `contrarian`
- `active_platform` (enum): `linkedin`, `x_thread`, `medium`
- `chaos_injection_flag` (enum): `NONE`, `INFINITE_LOOP`, `REJECT_SCHEMA_OUTPUT`
- `thread_id` (string, optional): Resume from checkpoint
- `media` (file, optional): Audio/video file for transcription

**Streaming Events:**
- `start` - Pipeline initiated
- `step` - Node progress (01, 02, etc.)
- `result` - Final state payload
- `error` - Failure notification

### `GET /api/health`

Health check endpoint returning status, database connection, and configuration.

### `GET /api/history/{thread_id}`

Retrieve checkpointed state history for a thread.

### Legacy Endpoints

- `GET /health` - Liveness probe
- `POST /run` - Non-streaming execution (deprecated, use streaming API)

---

## Strategic Angles

| Angle | Target Audience | Focus Direction |
|-------|-----------------|-----------------|
| **Recruiter** | Senior engineering recruiters & hiring managers | Frame technical depth as rare talent signal |
| **Technical** | AI/ML engineers building production systems | Emphasize architecture, failure modes, trade-offs |
| **Founder** | Technical founders & indie hackers | Build-in-public narrative with lessons learned |
| **Contrarian** | Experienced practitioners skeptical of hype | Challenge consensus with evidence-backed claims |

---

## Development

### Backend

```bash
# Run with reload
uvicorn app.main:app --reload

# Run with specific port
uvicorn app.main:app --reload --port 8080

# Run in production mode
ENVIRONMENT=production uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Frontend

```bash
cd frontend
npm run dev      # Development server
npm run build    # Production build
npm run preview  # Preview production build
npm run typecheck  # TypeScript type check
npm run lint     # ESLint
```

### Testing

```bash
# Frontend type checking
cd frontend && npm run typecheck

# Backend linting (install ruff for Python linting)
cd backend && ruff check app/
```

---

## Dependencies

### Backend

- **FastAPI** - Modern web framework
- **LangGraph** - State machine for agent workflows
- **LiteLLM** - LLM abstraction layer with failover
- **Instructor** - Structured output via Pydantic
- **Mistral AI SDK** - Voxtral transcription

### Frontend

- **React 18** - Component library
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Utility-first CSS framework
- **Vite** - Build tool
- **Lucide React** - Icon library
- **Mermaid** - Diagram rendering

---

## Deployment Architecture

### Production Stack

```
┌─────────────────────────────────────────────────────┐
│                    Vercel (Frontend)                 │
│  https://meta-pro-five.vercel.app                      │
└─────────────────────┬─────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│                 Render (Backend)                     │
│  FastAPI + Uvicorn on Python 3.11                    │
│  Auto-deploy on push via Blueprint                   │
└─────────────────────┬─────────────────────────────────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────┐
│ Supabase │   │  LiteLLM │   │  Mistral │
│ PostgreSQL│  │  Router  │   │   API    │
│ Checkpoint│  │  (Rate   │   │  (LLM +  │
│   Storage │   │  Limit)  │   │ Transcrip│
└──────────┘   └──────────┘   │   tion)    │
                              └──────────┘
```

---

## Troubleshooting

### Backend won't start in production

Ensure `DATABASE_URL` and `MISTRAL_API_KEY` are set in your Render dashboard under Settings → Environment.

### API returns 429 Rate Limited

Adjust `MIN_LLM_INTERVAL_SECONDS` in your `.env` file. Higher values (30-60 seconds) reduce request volume.

### Transcript upload fails

- Maximum file size: 100MB
- Supported formats: MP4, MP3, WAV, M4A, etc.
- Check `MAX_MEDIA_BYTES` in frontend code