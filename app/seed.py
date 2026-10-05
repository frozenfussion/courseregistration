"""First-run data: the Claude for Builders course, taken from the trainer's own course outline.

Dates, venue and fee are intentionally left empty so the public page shows "To be announced" until they
are filled in through the admin.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Course
from app.services import activate_course

INTRODUCTION = (
    "This two-day course is for participants who already use Claude as a productivity assistant and are "
    "ready to use it in more technical, structured and operational ways. It extends that foundation into "
    "development workflows, API usage, tool calling, automation, Claude Code, MCP and production-aware "
    "implementation.\n\n"
    "The emphasis is practical: how developers, analysts and automation teams can use Claude safely and "
    "effectively to build workflows, accelerate coding tasks, connect external systems and design "
    "AI-assisted solutions that survive real workplace constraints."
)

OUTCOMES = [
    "Understand how Claude fits into technical workflows beyond ordinary prompting",
    "Use the Claude API for structured application-level interactions",
    "Understand authentication, request structure, response handling, tokens, limits and model selection",
    "Design better technical prompts for APIs, automation and repeatable workflows",
    "Use tool calling concepts to connect Claude with external functions, systems and APIs",
    "Understand client-side tools, server-side tools and MCP-based integration patterns",
    "Use Claude Code concepts for AI-assisted software development workflows",
    "Apply context management, project memory, custom commands, hooks, skills and subagents",
    "Understand MCP architecture, servers, clients, tools, resources and prompts",
    "Identify when to use Claude directly, through cloud platforms, through coding agents, or through MCP",
    "Apply security, privacy, governance and review practices for technical AI usage",
    "Plan practical adoption patterns for teams building with Claude in professional environments",
]

PREREQUISITES = [
    "Completion of a basic Claude productivity course or equivalent hands-on Claude usage",
    "General understanding of prompts, context, iteration and responsible AI review",
    "Basic coding knowledge in Python, JavaScript, TypeScript or a similar language",
    "Basic familiarity with APIs, JSON, HTTP requests and response structures",
    "Comfort using a code editor such as VS Code",
    "Basic command-line or terminal usage",
    "Basic Git and version control awareness",
    "General understanding of cloud or web application concepts",
    "A Claude account, Claude API key, or access to an approved organizational Claude environment",
    "Awareness of basic data privacy, credential handling and workplace security practices",
]

AUDIENCE = [
    "Software developers beginning to adopt Claude in development workflows",
    "Technical analysts and automation specialists",
    "Data professionals who need AI-assisted scripting and workflow automation",
    "DevOps, platform and cloud engineers exploring Claude integration",
    "Solution architects and technical leads evaluating Claude for internal applications",
    "Product teams working with AI-enabled features",
    "IT professionals responsible for controlled AI adoption",
    "Power users ready to move from prompt-based productivity into APIs, tools and automation",
    "Teams preparing to build internal AI assistants, coding workflows or MCP-connected systems",
]

OUTLINE = [
    ("Technical Foundations for Building with Claude", [
        "Moving from productivity use to technical implementation", "Claude technical ecosystem overview",
        "Model selection and capability awareness", "Technical AI collaboration mindset"]),
    ("Claude Platform and API Fundamentals", [
        "Claude Platform orientation", "API architecture fundamentals", "Authentication and access control",
        "Request and response structure", "Messages API workflow", "SDK-based development"]),
    ("Prompt Engineering for Technical Systems", [
        "Prompt design for API workflows", "Structured outputs", "Technical task decomposition",
        "Context management for applications", "Reliability and quality controls"]),
    ("Tool Use and Function Calling with Claude", [
        "Tool use concepts", "Tool calling workflow", "Schema design for tools", "Tool choice control",
        "Server tools and built-in capabilities", "Production considerations for tool use"]),
    ("Building Claude-Powered Applications", [
        "Application architecture patterns", "Backend integration patterns", "Conversation and session design",
        "Data handling and file workflows", "Cost and performance management", "Testing and evaluation"]),
    ("Claude Code for AI-Assisted Development", [
        "Claude Code fundamentals", "Claude Code setup and usage", "Daily development workflows",
        "Context management in Claude Code", "Project memory and instruction files",
        "Planning and permission modes", "Code review and Git workflows"]),
    ("Extending Claude Code", ["Custom commands", "Hooks", "Skills", "Subagents", "Claude Code SDK"]),
    ("Model Context Protocol Fundamentals", [
        "MCP purpose and positioning", "MCP architecture", "MCP core primitives", "Building MCP servers",
        "Building MCP clients", "MCP resources", "MCP prompts", "Advanced MCP considerations"]),
    ("Cloud Platform Integration", [
        "Claude deployment options", "AWS integration concepts", "Google Cloud integration concepts",
        "Azure and managed platform concepts", "Choosing an integration path"]),
    ("Security, Privacy, and Governance for Technical Claude Use", [
        "Data protection foundations", "Access control", "Prompt injection and tool security",
        "Secure coding with Claude", "Governance and operational readiness"]),
    ("Practical Technical Adoption", [
        "Team workflow design", "Internal enablement", "Use case selection", "Implementation planning",
        "Ongoing improvement"]),
]


def seed_default_course(db: Session) -> Course | None:
    """Create and activate the starter course, only if there are no courses yet."""
    if db.scalar(select(func.count()).select_from(Course)):
        return None
    course = Course(
        slug="claude-for-builders-and-technical-teams",
        title="Claude for Builders and Technical Teams",
        accent_word="Builders",
        tagline="From AI productivity to API-driven workflows, coding agents, MCP, and enterprise integration.",
        introduction=INTRODUCTION,
        outcomes=OUTCOMES,
        prerequisites=PREREQUISITES,
        audience=AUDIENCE,
        outline=[{"title": t, "topics": topics} for t, topics in OUTLINE],
        duration_text="2 days",
        fee_note="HRD Corp claimable",
        capacity=30,
    )
    db.add(course)
    db.commit()
    activate_course(db, course)
    return course
