# ContentForge AI

> Agentic AI-powered content creation platform that researches, plans, writes, optimizes, repurposes, and publishes content automatically.

ContentForge AI is a multi-agent content generation system built using **LangGraph**, **LangChain**, **OpenAI**, **Tavily**, **Streamlit**, and **Dev.to APIs**.

The platform goes far beyond simple blog generation. It performs research, competitor analysis, content-gap discovery, SEO optimization, image generation, social media repurposing, and one-click publishing.

WORKING LINK - https://contentforge-ai.streamlit.app/


---

# Live Features

✅ AI Blog Generation

✅ Autonomous Research Pipeline

✅ Competitor Analysis Agent

✅ Content Gap Discovery Agent

✅ SEO Strategy Agent

✅ SEO Audit Agent

✅ Technical Diagram Generation

✅ LinkedIn Content Generation

✅ Twitter/X Thread Generation

✅ Newsletter Generation

✅ Instagram Carousel Content Generation

✅ AI Image Generation for Social Media

✅ One-Click Publishing to Dev.to

✅ Interactive Agent Execution Logs

✅ Downloadable Markdown Content

---

# Tech Stack

## AI & Agent Framework

- LangGraph
- LangChain
- OpenAI GPT-4o Mini
- Tavily Search API

## Frontend

- Streamlit

## Image Generation

- Google Gemini 2.5 Flash Image

## Publishing

- Dev.to API

## Monitoring

- LangSmith 

## Infrastructure

- Python
- Pydantic
- Markdown

---

# System Architecture

The project follows a multi-agent architecture where every agent is responsible for a specialized task.

```text
User Topic
    │
    ▼
Router Agent
    │
    ├── Research Required?
    │
    ▼
Research Agent
    │
    ▼
Competitor Analysis Agent
    │
    ▼
Content Gap Agent
    │
    ▼
SEO Strategy Agent
    │
    ▼
Orchestrator Agent
    │
    ▼
Worker Agents (Parallel)
    │
    ▼
Reducer
    │
    ▼
Image Planner
    │
    ▼
Image Generator
    │
    ▼
SEO Audit Agent
    │
    ▼
Final Blog
```

---

# Agent Pipeline

---

## 1. Router Agent

Determines:

- Whether web research is required
- Content generation mode
- Research queries

### Modes

#### Closed Book

Used for evergreen topics.

Example:

```text
What is Retrieval Augmented Generation?
```

No external research required.

---

#### Hybrid

Used when current examples are useful.

Example:

```text
LangGraph Tutorial
```

Research + LLM knowledge.

---

#### Open Book

Used for highly dynamic topics.

Example:

```text
Latest AI developments this week
```

Requires fresh web research.

---

# 2. Research Agent

Uses Tavily Search API.

Responsibilities:

- Collect authoritative sources
- Filter irrelevant pages
- Deduplicate results
- Extract evidence

Output:

```python
EvidenceItem
```

Contains:

- title
- url
- snippet
- publish date

---

# 3. Competitor Analysis Agent

Analyzes top ranking content.

Identifies:

- Common topics
- Common headings
- Frequently covered concepts
- Competitor strengths
- Competitor weaknesses

Example:

```text
Topic:
Agentic AI
```

Finds:

```text
Most competitors discuss:
- Autonomous workflows
- Tool calling
- Memory

Few discuss:
- Production deployment
- Cost optimization
```

---

# 4. Content Gap Agent

Uses competitor insights.

Discovers:

### Must Cover Topics

Topics expected by readers.

### Gap Opportunities

Valuable information competitors ignore.

### Unique Angles

Ways to differentiate content.

### Recommended Sections

Additional sections that improve ranking potential.

---

# 5. SEO Strategy Agent

Creates a content ranking strategy.

Generates:

- Primary keyword
- Secondary keywords
- Search intent
- Recommended headings
- Audience targeting

Example:

```text
Primary Keyword:
Agentic AI

Secondary Keywords:
- langgraph
- ai agents
- autonomous workflows
```

---

# 6. Orchestrator Agent

Creates the master content plan.

Produces:

```python
Plan
```

Contains:

- Blog structure
- Section goals
- Writing instructions
- Word targets

---

# 7. Worker Agents

Executed in parallel.

Each worker writes one section.

Responsibilities:

- Follow SEO strategy
- Use research evidence
- Cover content gaps
- Add citations when required

This significantly reduces generation time.

---

# 8. Reducer

Combines worker outputs.

Creates:

```markdown
# Blog Title

Section 1

Section 2

Section 3
```

---

# 9. Image Planning Agent

Analyzes final content.

Determines:

- Whether images are needed
- Where images should be placed
- Image prompts

Generates placeholders:

```text
[[IMAGE_1]]
[[IMAGE_2]]
```

---

# 10. Image Generation Agent

Uses Gemini Image Model.

Creates:

- Technical diagrams
- Workflow illustrations
- Architecture visuals

Automatically injects generated images into content.

### Fallback Handling

If image generation fails:

- Blog generation continues
- No crash occurs
- Content remains usable

---

# 11. SEO Audit Agent

Analyzes completed article.

Generates:

### SEO Title

```text
Best Agentic AI Guide for Developers
```

### Meta Description

### URL Slug

### Reading Time

### SEO Score

### Strengths

### Improvements

### FAQ Section

---

# Multi-Platform Content Generation

After blog creation, users can repurpose content into multiple formats.

---

## LinkedIn Agent

Generates:

- Professional LinkedIn post
- Industry-focused messaging
- Engagement hooks
- CTA

Also generates:

- LinkedIn visual image

---

## Twitter/X Agent

Generates:

- Complete thread
- Tweet numbering
- Short-form content
- Viral formatting

---

## Newsletter Agent

Generates:

- Subject line
- Newsletter body
- Reader-focused summaries

---

## Instagram Agent

Generates:

- Carousel slide content
- Captions
- Hashtags

Also generates:

- Instagram visual

---

# Dev.to Publishing Agent

After content generation:

User can choose:

```text
Publish to Dev.to
```

The application requests:

- Dev.to API Key

Then automatically:

1. Extracts SEO keywords
2. Generates valid Dev.to tags
3. Creates article payload
4. Publishes article

### Automated Tag Optimization

Tags are generated from:

```text
Primary Keyword
Secondary Keywords
```

And transformed into:

```text
lowercase
no spaces
max 3 tags
```

Example:

```text
Agentic AI
LangGraph
AI Agents
```

Becomes:

```text
agenticai
langgraph
aiagents
```

---

# Streamlit Interface

The application includes:

### Dashboard

- Content generation controls
- Agent status monitoring
- Blog preview

### Agent Execution Logs

Displays:

- Active node
- Execution progress
- State updates

### SEO Analytics Panel

Shows:

- SEO score
- Keywords
- Meta description

### Publishing Panel

Allows:

- Dev.to publishing
- Content repurposing

---

# Project Structure

```text
contentforge-ai/

│
├── bwa_backend.py
│   ├── LangGraph Workflow
│   ├── Agent Logic
│   ├── SEO Pipeline
│   ├── Research Pipeline
│
├── bwa_frontend.py
│   ├── Streamlit UI
│   ├── Content Generation
│   ├── Publishing Controls
│
├── publish_agent.py
│   ├── Dev.to Publishing
│   ├── SEO Tag Extraction
│
├── requirements.txt
│
└── README.md
```

---

# Installation

Clone repository:

```bash
git clone https://github.com/<username>/contentforge-ai.git

cd contentforge-ai
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run application:

```bash
streamlit run bwa_frontend.py
```

---

# Environment Variables

Create:

```text
.env
```

```env
OPENAI_API_KEY=your_key

TAVILY_API_KEY=your_key

GOOGLE_API_KEY=your_key

LANGCHAIN_API_KEY=your_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=ContentForgeAI
```

---

# Future Enhancements

- WordPress Publishing Agent
- Medium Publishing Agent
- Ghost CMS Integration
- Automated Content Scheduling
- Analytics Feedback Loop
- Content Performance Optimization Agent
- Multi-language Content Generation
- AI Content Calendar Agent
- Brand Voice Memory System
- RAG-based Knowledge Base Integration

---

# Why This Project Matters

ContentForge AI demonstrates production-level Agentic AI concepts:

- Multi-Agent Architectures
- Agent Collaboration
- Structured Outputs
- Autonomous Research
- SEO Optimization
- Content Gap Discovery
- Publishing Automation
- Human-in-the-Loop Workflows
- LangGraph State Management
- Real-world Business Automation

This project showcases how multiple AI agents can work together to execute an end-to-end content creation workflow that traditionally requires an entire content marketing team.
