from __future__ import annotations
import operator
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import TypedDict, List, Optional, Literal, Annotated
from pydantic import BaseModel, Field
from enum import Enum
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Blog Writer (Router → (Research?) → Orchestrator → Workers → ReducerWithImages)
# Patches image capability using your 3-node reducer flow:
#   merge_content -> decide_images -> generate_and_place_images
# ============================================================


# -----------------------------
# 1) Schemas
# -----------------------------
class Task(BaseModel):
    id: int
    title: str
    goal: str = Field(..., description="One sentence describing what the reader should do/understand.")
    bullets: List[str] = Field(..., min_length=3, max_length=6)
    target_words: int = Field(..., description="Target words (120–550).")

    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task]


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None  # ISO "YYYY-MM-DD" preferred
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: List[str] = Field(default_factory=list)
    max_results_per_query: int = Field(5)


class EvidencePack(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)


# ---- Image planning schema (ported from your image flow) ----
class ImageSpec(BaseModel):
    placeholder: str = Field(..., description="e.g. [[IMAGE_1]]")
    filename: str = Field(..., description="Save under images/, e.g. qkv_flow.png")
    alt: str
    caption: str
    prompt: str = Field(..., description="Prompt to send to the image model.")
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "medium"


class GlobalImagePlan(BaseModel):
    md_with_placeholders: str
    images: List[ImageSpec] = Field(default_factory=list)

class State(TypedDict):
    topic: str

    # routing / research
    mode: str
    needs_research: bool
    queries: List[str]
    evidence: List[EvidenceItem]
    plan: Optional[Plan]
    #competitor analysis
    competitor_analysis: Optional[CompetitorAnalysis]
    content_gap_analysis: Optional[ContentGapAnalysis]

    #seo plans strategy 
    seo_strategy: Optional[SEOStrategy]


    # recency
    as_of: str
    recency_days: int

    # workers
    sections: Annotated[List[tuple[int, str]], operator.add]  # (task_id, section_md)

    # reducer/image
    merged_md: str
    md_with_placeholders: str
    image_specs: List[dict]

    final: str
    #seo audit 
    seo_audit: Optional[SEOAudit]



class CompetitorAnalysis(BaseModel):
    competitor_urls: List[str]

    common_topics: List[str]

    common_headings: List[str]

    observed_strengths: List[str]

    observed_weaknesses: List[str]



class SEOStrategy(BaseModel):
    primary_keyword: str

    secondary_keywords: List[str] = Field(
        default_factory=list,
        max_length=10
    )

    search_intent: Literal[
        "informational",
        "commercial",
        "transactional",
        "navigational"
    ]

    target_audience: str

    recommended_headings: List[str] = Field(
        default_factory=list
    )


class ContentGapAnalysis(BaseModel):
    must_cover_topics: List[str]

    gap_opportunities: List[str]

    unique_angles: List[str]

    recommended_additional_sections: List[str]



class SEOAudit(BaseModel):
    seo_title: str

    meta_description: str

    slug: str

    estimated_reading_time: int

    seo_score: int = Field(
        description="Score between 0 and 100"
    )

    strengths: List[str]

    improvements: List[str]

    faq_section: str


# -----------------------------
# Social Content Models
# -----------------------------
class BlogPackage(BaseModel):
    topic: str
    blog_content: str
    seo_strategy: dict
    seo_audit: dict
    competitor_analysis: dict
    content_gap_analysis: dict


class PlatformType(str, Enum):
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    NEWSLETTER = "newsletter"
    INSTAGRAM = "instagram"


class LinkedInContent(BaseModel):
    hook: str
    body: str
    call_to_action: str
    hashtags: List[str]
    image_prompt: str


class TwitterThread(BaseModel):
    tweets: List[str]


class NewsletterContent(BaseModel):
    subject_line: str
    preview_text: str
    body: str


class InstagramCarousel(BaseModel):
    slide_titles: List[str]
    slide_contents: List[str]
    caption: str
    hashtags: List[str]
    image_prompt: str




# -----------------------------
# 2) LLM
# -----------------------------
llm = ChatOpenAI(model="gpt-4o-mini")

# -----------------------------
# 3) Router
# -----------------------------
ROUTER_SYSTEM = """You are a routing module for a technical blog planner.

Decide whether web research is needed BEFORE planning.

Modes:
- closed_book (needs_research=false): evergreen concepts.
- hybrid (needs_research=true): evergreen + needs up-to-date examples/tools/models.
- open_book (needs_research=true): volatile weekly/news/"latest"/pricing/policy.

If needs_research=true:
- Output 3–10 high-signal, scoped queries.
- For open_book weekly roundup, include queries reflecting last 7 days.
"""

def router_node(state: State) -> dict:
    decider = llm.with_structured_output(RouterDecision)
    decision = decider.invoke(
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=f"Topic: {state['topic']}\nAs-of date: {state['as_of']}"),
        ]
    )

    if decision.mode == "open_book":
        recency_days = 7
    elif decision.mode == "hybrid":
        recency_days = 45
    else:
        recency_days = 3650

    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "queries": decision.queries,
        "recency_days": recency_days,
    }

def route_next(state: State) -> str:
    return "research" if state["needs_research"] else "competitor_analysis"

# -----------------------------
# 4) Research (Tavily)
# -----------------------------
def _tavily_search(query: str, max_results: int = 5) -> List[dict]:
    if not os.getenv("TAVILY_API_KEY"):
        return []
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults  # type: ignore
        tool = TavilySearchResults(max_results=max_results)
        results = tool.invoke({"query": query})
        out: List[dict] = []
        for r in results or []:
            out.append(
                {
                    "title": r.get("title") or "",
                    "url": r.get("url") or "",
                    "snippet": r.get("content") or r.get("snippet") or "",
                    "published_at": r.get("published_date") or r.get("published_at"),
                    "source": r.get("source"),
                }
            )
        return out
    except Exception:
        return []

def _iso_to_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None

RESEARCH_SYSTEM = """You are a research synthesizer.

Given raw web search results, produce EvidenceItem objects.

Rules:
- Only include items with a non-empty url.
- Prefer relevant + authoritative sources.
- Normalize published_at to ISO YYYY-MM-DD if reliably inferable; else null (do NOT guess).
- Keep snippets short.
- Deduplicate by URL.
"""

def research_node(state: State) -> dict:
    queries = (state.get("queries") or [])[:10]
    raw: List[dict] = []
    for q in queries:
        raw.extend(_tavily_search(q, max_results=6))

    if not raw:
        return {"evidence": []}

    extractor = llm.with_structured_output(EvidencePack)
    pack = extractor.invoke(
        [
            SystemMessage(content=RESEARCH_SYSTEM),
            HumanMessage(
                content=(
                    f"As-of date: {state['as_of']}\n"
                    f"Recency days: {state['recency_days']}\n\n"
                    f"Raw results:\n{raw}"
                )
            ),
        ]
    )

    dedup = {}
    for e in pack.evidence:
        if e.url:
            dedup[e.url] = e
    evidence = list(dedup.values())

    if state.get("mode") == "open_book":
        as_of = date.fromisoformat(state["as_of"])
        cutoff = as_of - timedelta(days=int(state["recency_days"]))
        evidence = [e for e in evidence if (d := _iso_to_date(e.published_at)) and d >= cutoff]

    return {"evidence": evidence}

#-----------------------------
#5) COMPETITOR ANALYSIS
#-----------------------------
COMPETITOR_ANALYSIS_SYSTEM = """
You are a senior content strategist.

Analyze the provided competitor articles.

Determine:

- Common headings
- Common topics
- Average content depth
- Competitor strengths
- Competitor weaknesses

Do not invent information.

Use only provided sources.

Return structured output.
"""


def competitor_analysis_node(state: State):
    
    if not state.get("evidence"):
        return {
            "competitor_analysis": CompetitorAnalysis(
                competitor_urls=[],
                common_topics=[],
                common_headings=[],
                observed_strengths=[],
                observed_weaknesses=[]
            )
        }
    extractor = llm.with_structured_output(
        CompetitorAnalysis
    )

    evidence_text = "\n\n".join(
        f"""
        Title: {e.title}

        URL: {e.url}

        Snippet:
        {e.snippet}
        """
        for e in state.get("evidence", [])
    )
    
    analysis = extractor.invoke(
        [
            SystemMessage(
                content=COMPETITOR_ANALYSIS_SYSTEM
            ),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"{evidence_text}"
                )
            )
        ]
    )

    return {
        "competitor_analysis": analysis
    }

#-----------------------
#5) CONTENT GAP AGENT
#----------------------
CONTENT_GAP_SYSTEM = """
You are a content gap analyst.

Using the competitor analysis:

Determine:

1. Topics that MUST be covered.
2. Missing opportunities.
3. Unique angles.
4. Additional sections that would improve the article.

Focus on differentiation.

Return structured output.
"""

def content_gap_node(state: State):

    competitor = state["competitor_analysis"]
    if not competitor.common_topics:

        return {
            "content_gap_analysis": ContentGapAnalysis(
                must_cover_topics=[],
                gap_opportunities=[],
                unique_angles=[],
                recommended_additional_sections=[]
            )
        }
    extractor = llm.with_structured_output(
        ContentGapAnalysis
    )

    gap = extractor.invoke(
        [
            SystemMessage(
                content=CONTENT_GAP_SYSTEM
            ),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"{competitor.model_dump_json(indent=2)}"
                )
            )
        ]
    )

    return {
        "content_gap_analysis": gap
    }


# -----------------------------
# 5) SEO STRATEGY AGENT
# -----------------------------
SEO_STRATEGY_SYSTEM = """
You are a senior SEO strategist.

Your job is to create an SEO strategy for a blog article.

You will receive:

1. Topic
2. Research evidence
3. Competitor analysis
4. Content gap analysis

Objectives:

- Determine the primary keyword.
- Determine secondary keywords.
- Identify search intent.
- Recommend section headings.
- Ensure the strategy covers important competitor topics.
- Ensure the strategy leverages content gaps and unique opportunities.
- Avoid recommending content that duplicates competitors unnecessarily.

Prioritize:
1. Search intent satisfaction.
2. Topic completeness.
3. Competitive differentiation.
4. Natural keyword usage.

The generated strategy should help the planner create a blog that is:
- Comprehensive
- SEO friendly
- Differentiated from competitors

Return structured output only.
"""

def seo_strategy_node(state: State):

    extractor = llm.with_structured_output(
        SEOStrategy
    )

    evidence_text = "\n".join(
        f"{e.title} | {e.url}"
        for e in state.get("evidence", [])
    )

    strategy = extractor.invoke(
        [
            SystemMessage(
                content=SEO_STRATEGY_SYSTEM
            ),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"Evidence:\n{evidence_text}\n"
                    f"competitor analysis:\n{state['competitor_analysis']}\n"
                    f"Content Gap: \n{state['content_gap_analysis']}\n"
                )
            )
        ]
    )

    return {
        "seo_strategy": strategy
    }







# -----------------------------
# 5) Orchestrator (Plan)
# -----------------------------
ORCH_SYSTEM = """You are a senior technical writer and developer advocate.
Produce a highly actionable outline for a technical blog post.
Requirements:
- 5–9 tasks, each with goal + 3–6 bullets + target_words.
- Tags are flexible; do not force a fixed taxonomy.
Grounding:
- closed_book: evergreen, no evidence dependence.
- hybrid: use evidence for up-to-date examples; mark those tasks requires_research=True and requires_citations=True.
- open_book: weekly/news roundup:
  - Set blog_kind="news_roundup"
  - No tutorial content unless requested
  - If evidence is weak, plan should explicitly reflect that (don’t invent events).

- Cover must_cover_topics.
- Include at least two gap opportunities.
- Include at least one unique angle.
Output must match Plan schema.
"""

def orchestrator_node(state: State) -> dict:
    planner = llm.with_structured_output(Plan)
    mode = state.get("mode", "closed_book")
    evidence = state.get("evidence", [])
    seo = state.get("seo_strategy")
    forced_kind = "news_roundup" if mode == "open_book" else None
    plan = planner.invoke(
        [
            SystemMessage(content=ORCH_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n"
                    f"Mode: {mode}\n"
                    f"As-of: {state['as_of']} (recency_days={state['recency_days']})\n"
                    f"{'Force blog_kind=news_roundup' if forced_kind else ''}\n\n"
                    f"Evidence:\n{[e.model_dump() for e in evidence][:16]}\n\n"
                    f"SEO Strategy: Primary Keyword:{seo.primary_keyword} \nSecondary Keywords:{seo.secondary_keywords}\nIntent:{seo.search_intent}\nRecommended Headings:{seo.recommended_headings}\n"
                    f"competitor analysis:\n{state['competitor_analysis']}\n"
                    f"Content Gap: \n{state['content_gap_analysis']}\n"

                )
            ),
        ]
    )
    if forced_kind:
        plan.blog_kind = "news_roundup"

    return {"plan": plan}


# -----------------------------
# 6) Fanout
# -----------------------------
def fanout(state: State):
    assert state["plan"] is not None
    return [
        Send(
            "worker",
            {
                "task": task.model_dump(),
                "topic": state["topic"],
                "mode": state["mode"],
                "as_of": state["as_of"],
                "recency_days": state["recency_days"],
                "plan": state["plan"].model_dump(),
                "evidence": [e.model_dump() for e in state.get("evidence", [])],
                "seo_strategy": state["seo_strategy"].model_dump(),
                "content_gap_analysis":state["content_gap_analysis"].model_dump(),
            },
        )
        for task in state["plan"].tasks
        
    ]

# -----------------------------
# 7) Worker
# -----------------------------
WORKER_SYSTEM = """You are a senior technical writer and developer advocate.
Write ONE section of a technical blog post in Markdown.

Constraints:
- Cover ALL bullets in order.
- Target words ±15%.
- Output only section markdown starting with "## <Section Title>".

Scope guard:
- If blog_kind=="news_roundup", do NOT drift into tutorials (scraping/RSS/how to fetch).
  Focus on events + implications.

Grounding:
- If mode=="open_book": do not introduce any specific event/company/model/funding/policy claim unless supported by provided Evidence URLs.
  For each supported claim, attach a Markdown link ([Source](URL)).
  If unsupported, write "Not found in provided sources."
- If requires_citations==true (hybrid tasks): cite Evidence URLs for external claims.

Code:
- If requires_code==true, include at least one minimal snippet.
SEO:
- Naturally include primary keyword.
- Use secondary keywords where relevant.
- Never keyword stuff.
Differentiation Requirements:
Use content gap analysis when relevant.
If your section aligns with a gap opportunity,
explicitly emphasize insights competitors often miss.
If unique angles are provided,
incorporate them naturally.
Avoid simply repeating commonly covered topics.
"""

def worker_node(payload: dict) -> dict:
    task = Task(**payload["task"])
    plan = Plan(**payload["plan"])
    evidence = [EvidenceItem(**e) for e in payload.get("evidence", [])]
    seo = payload["seo_strategy"]
    gap_analysis = payload.get(
    "content_gap_analysis",
    {}
    )
    bullets_text = "\n- " + "\n- ".join(task.bullets)
    evidence_text = "\n".join(
        f"- {e.title} | {e.url} | {e.published_at or 'date:unknown'}"
        for e in evidence[:20]
    )

    section_md = llm.invoke(
        [
            SystemMessage(content=WORKER_SYSTEM),
            HumanMessage(
                content=(
                    f"Blog title: {plan.blog_title}\n"
                    f"Audience: {plan.audience}\n"
                    f"Tone: {plan.tone}\n"
                    f"Blog kind: {plan.blog_kind}\n"
                    f"Constraints: {plan.constraints}\n"
                    f"Topic: {payload['topic']}\n"
                    f"Mode: {payload.get('mode')}\n"
                    f"As-of: {payload.get('as_of')} (recency_days={payload.get('recency_days')})\n\n"
                    f"Section title: {task.title}\n"
                    f"Goal: {task.goal}\n"
                    f"Target words: {task.target_words}\n"
                    f"Tags: {task.tags}\n"
                    f"requires_research: {task.requires_research}\n"
                    f"requires_citations: {task.requires_citations}\n"
                    f"requires_code: {task.requires_code}\n"
                    f"Bullets:{bullets_text}\n\n"
                    f"Evidence (ONLY cite these URLs):\n{evidence_text}\n"
                    f"SEO Primary Keyword:{seo['primary_keyword']} \n SEO Secondary Keywords:{seo['secondary_keywords']}"
                    f"Content Gap Analysis Must Cover Topics:{gap_analysis['must_cover_topics']}"
                    f"Gap Opportunities:{gap_analysis['gap_opportunities']}"
                    f"Unique Angles:{gap_analysis['unique_angles']}"
                    f"Recommended Additional Sections:{gap_analysis['recommended_additional_sections']}"
                )
            ),
        ]
    ).content.strip()

    return {"sections": [(task.id, section_md)]}

# ============================================================
# 8) ReducerWithImages (subgraph)
#    merge_content -> decide_images -> generate_and_place_images
# ============================================================
def merge_content(state: State) -> dict:
    plan = state["plan"]
    if plan is None:
        raise ValueError("merge_content called without plan.")
    ordered_sections = [md for _, md in sorted(state["sections"], key=lambda x: x[0])]
    body = "\n\n".join(ordered_sections).strip()
    merged_md = f"# {plan.blog_title}\n\n{body}\n"
    return {"merged_md": merged_md}


DECIDE_IMAGES_SYSTEM = """You are an expert technical editor.
Decide if images/diagrams are needed for THIS blog.

Rules:
- Max 3 images total.
- Each image must materially improve understanding (diagram/flow/table-like visual).
- Insert placeholders exactly: [[IMAGE_1]], [[IMAGE_2]], [[IMAGE_3]].
- If no images needed: md_with_placeholders must equal input and images=[].
- Avoid decorative images; prefer technical diagrams with short labels.
Return strictly GlobalImagePlan.
"""

def decide_images(state: State) -> dict:
    planner = llm.with_structured_output(GlobalImagePlan)
    merged_md = state["merged_md"]
    plan = state["plan"]
    assert plan is not None

    image_plan = planner.invoke(
        [
            SystemMessage(content=DECIDE_IMAGES_SYSTEM),
            HumanMessage(
                content=(
                    f"Blog kind: {plan.blog_kind}\n"
                    f"Topic: {state['topic']}\n\n"
                    "Insert placeholders + propose image prompts.\n\n"
                    f"{merged_md}"
                )
            ),
        ]
    )

    return {
        "md_with_placeholders": image_plan.md_with_placeholders,
        "image_specs": [img.model_dump() for img in image_plan.images],
    }


def _gemini_generate_image_bytes(prompt: str) -> bytes:
    """
    Returns raw image bytes generated by Gemini.
    Requires: pip install google-genai
    Env var: GOOGLE_API_KEY
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_ONLY_HIGH",
                )
            ],
        ),
    )

    # Depending on SDK version, parts may hang off resp.candidates[0].content.parts
    parts = getattr(resp, "parts", None)
    if not parts and getattr(resp, "candidates", None):
        try:
            parts = resp.candidates[0].content.parts
        except Exception:
            parts = None

    if not parts:
        raise RuntimeError("No image content returned (safety/quota/SDK change).")

    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            return inline.data

    raise RuntimeError("No inline image bytes found in response.")


def _safe_slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "blog"


def generate_and_place_images(state: State) -> dict:
    plan = state["plan"]
    assert plan is not None

    md = state.get("md_with_placeholders") or state["merged_md"]
    image_specs = state.get("image_specs", []) or []

    # If no images requested, just write merged markdown
    if not image_specs:
    #     filename = f"{_safe_slug(plan.blog_title)}.md"
    #     Path(filename).write_text(md, encoding="utf-8")
        return {"final": md}

    images_dir = Path("images")
    images_dir.mkdir(exist_ok=True)

    for spec in image_specs:
        placeholder = spec["placeholder"]
        filename = spec["filename"]
        out_path = images_dir / filename

        # generate only if needed
        if not out_path.exists():
            try:
                img_bytes = _gemini_generate_image_bytes(spec["prompt"])
                out_path.write_bytes(img_bytes)
            except Exception as e:
                # graceful fallback: keep doc usable
                prompt_block = (
                    f"> **[IMAGE GENERATION FAILED]** {spec.get('caption','')}\n>\n"
                    f"> **Alt:** {spec.get('alt','')}\n>\n"
                    f"> **Prompt:** {spec.get('prompt','')}\n>\n"
                    f"> **Error:** {e}\n"
                )
                md = md.replace(placeholder, prompt_block)
                continue

        img_md = f"![{spec['alt']}](images/{filename})\n*{spec['caption']}*"
        md = md.replace(placeholder, img_md)
    #this stores files in disk
    # filename = f"{_safe_slug(plan.blog_title)}.md"
    # Path(filename).write_text(md, encoding="utf-8")
    return {"final": md}



# ============================================================
# 9) SEO AUDIT
# ============================================================
SEO_AUDIT_SYSTEM = """
You are a senior SEO auditor.

Analyze the blog.

Generate:

- SEO title
- Meta description
- URL slug
- Reading time
- SEO score (0-100)
- Strengths
- Improvements

Also generate an FAQ section.

FAQ must be markdown.
"""


LINKEDIN_SYSTEM = """
You are an elite LinkedIn content strategist.

Transform the blog into a professional thought-leadership LinkedIn post.

Requirements:
- Strong opening hook.
- Professional tone.
- Focus on insights.
- Focus on lessons learned.
- Include CTA.
- Generate 5-10 hashtags.
- Generate infographic image prompt.

Output structured data only.
"""

TWITTER_SYSTEM = """
You are an expert Twitter/X thread writer.

Requirements:
- 5-12 tweets.
- Tweet 1 must be a hook.
- Educational.
- High engagement.
- around 70-80 word sentences.

Output structured data only.
"""

NEWSLETTER_SYSTEM = """
You are a newsletter editor.

Transform the article into a newsletter.

Requirements:
- Conversational.
- Educational.
- Professional.
- Strong subject line.
- Strong preview text.

Output structured data only.
"""

INSTAGRAM_SYSTEM = """
You are an Instagram content strategist.

Create an educational carousel.

Requirements:
- 5-10 slides.
- Concise text.
- Visual-first communication.
- Generate caption.
- Generate hashtags.
- Generate cover image prompt.

Output structured data only.
"""


def seo_audit_node(state: State):

    extractor = llm.with_structured_output(
        SEOAudit
    )

    audit = extractor.invoke(
        [
            SystemMessage(
                content=SEO_AUDIT_SYSTEM
            ),
            HumanMessage(
                content=state["final"]
            )
        ]
    )

    return {
        "seo_audit": audit
    }

#10) FINL FORMAT
def final_formatter_node(state: State):

    audit = state["seo_audit"]

    frontmatter = f"""---
    title: {audit.seo_title}
    description: {audit.meta_description}
    slug: {audit.slug}
    seo_score: {audit.seo_score}
    reading_time: {audit.estimated_reading_time}
    ---
    """

    blog = (
        frontmatter
        + "\n"
        + state["final"]
        + "\n\n"
        + audit.faq_section
    )

    return {
        "final": blog
    }


# ----------------------------------------
# Social Content Repurposing Utilities
# ----------------------------------------

def build_blog_package(state: State):
    return BlogPackage(
        topic=state["topic"],
        blog_content=state["final"],
        seo_strategy=state["seo_strategy"].model_dump(),
        seo_audit=state["seo_audit"].model_dump(),
        competitor_analysis=state["competitor_analysis"].model_dump(),
        content_gap_analysis=state["content_gap_analysis"].model_dump(),
    )


def build_package_context(package: BlogPackage):
    return f"""
Topic:
{package.topic}

SEO Strategy:
{package.seo_strategy}

SEO Audit:
{package.seo_audit}

Competitor Analysis:
{package.competitor_analysis}

Content Gap Analysis:
{package.content_gap_analysis}

Blog:
{package.blog_content}
"""


def generate_social_image(prompt: str, filename: str):
    social_dir = Path("social_images")
    social_dir.mkdir(exist_ok=True)

    try:
        img_bytes = _gemini_generate_image_bytes(prompt)

        if not img_bytes:
            return None

        path = social_dir / filename
        path.write_bytes(img_bytes)
        return str(path)

    except Exception as e:
        print(f"Image generation skipped: {e}")
        return None


def generate_linkedin(package: BlogPackage):
    extractor = llm.with_structured_output(LinkedInContent)
    return extractor.invoke(
        [
            SystemMessage(content=LINKEDIN_SYSTEM),
            HumanMessage(content=build_package_context(package))
        ]
    )


def generate_twitter(package: BlogPackage):
    extractor = llm.with_structured_output(TwitterThread)
    return extractor.invoke(
        [
            SystemMessage(content=TWITTER_SYSTEM),
            HumanMessage(content=build_package_context(package))
        ]
    )


def generate_newsletter(package: BlogPackage):
    extractor = llm.with_structured_output(NewsletterContent)
    return extractor.invoke(
        [
            SystemMessage(content=NEWSLETTER_SYSTEM),
            HumanMessage(content=build_package_context(package))
        ]
    )


def generate_instagram(package: BlogPackage):
    extractor = llm.with_structured_output(InstagramCarousel)
    return extractor.invoke(
        [
            SystemMessage(content=INSTAGRAM_SYSTEM),
            HumanMessage(content=build_package_context(package))
        ]
    )


def repurpose_content(
    package: BlogPackage,
    platform: PlatformType
):
    if platform == PlatformType.LINKEDIN:
        result = generate_linkedin(package)

        image = None
        if result.image_prompt:
            image = generate_social_image(
                result.image_prompt,
                "linkedin.png"
            )

        return {
            "content": result,
            "image": image
        }

    elif platform == PlatformType.TWITTER:
        return generate_twitter(package)

    elif platform == PlatformType.NEWSLETTER:
        return generate_newsletter(package)

    elif platform == PlatformType.INSTAGRAM:
        result = generate_instagram(package)

        image = None
        if result.image_prompt:
            image = generate_social_image(
                result.image_prompt,
                "instagram.png"
            )

        return {
            "content": result,
            "image": image
        }


def repurpose_multiple(
    package: BlogPackage,
    platforms: List[PlatformType]
):
    outputs = {}
    for platform in platforms:
        outputs[platform.value] = repurpose_content(
            package,
            platform
        )
    return outputs

# build reducer subgraph
reducer_graph = StateGraph(State)
reducer_graph.add_node("merge_content", merge_content)
reducer_graph.add_node("decide_images", decide_images)
reducer_graph.add_node("generate_and_place_images", generate_and_place_images)
reducer_graph.add_edge(START, "merge_content")
reducer_graph.add_edge("merge_content", "decide_images")
reducer_graph.add_edge("decide_images", "generate_and_place_images")
reducer_graph.add_edge("generate_and_place_images", END)
reducer_subgraph = reducer_graph.compile()

# -----------------------------
# 9) Build main graph
# -----------------------------
g = StateGraph(State)
g.add_node("router", router_node)
g.add_node("research", research_node)
g.add_node( "competitor_analysis", competitor_analysis_node)
g.add_node("content_gap",content_gap_node)
g.add_node("seo_strategy", seo_strategy_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker", worker_node)
g.add_node("reducer", reducer_subgraph)
g.add_node("seo_audit",seo_audit_node)
g.add_node( "final_formatter",final_formatter_node)





g.add_edge(START, "router")
g.add_conditional_edges( "router", route_next,
    {
        "research": "research",
        "competitor_analysis": "competitor_analysis"
    }
)
# g.add_edge("research","seo_strategy")
g.add_edge("research","competitor_analysis")
g.add_edge("competitor_analysis","content_gap")
g.add_edge("content_gap","seo_strategy")
g.add_edge("seo_strategy","orchestrator")
g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker", "reducer")
# g.add_edge("reducer", END)
g.add_edge("reducer","seo_audit")
g.add_edge("seo_audit","final_formatter")
g.add_edge("final_formatter",END)

app = g.compile()
app

