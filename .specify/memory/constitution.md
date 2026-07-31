<!--
  Sync Impact Report
  ==================
  Version change: (none) → 1.0.0 (initial constitution)
  
  Principles defined:
  - I. Test-Driven Development (TDD)
  - II. API-First Design
  - III. Separation of Concerns
  - IV. Database Integrity
  - V. Simplicity (YAGNI)
  
  Sections added:
  - Core Principles (5 principles)
  - Technology Stack
  - Development Workflow
  - Governance
  
  Templates requiring updates:
  - .specify/templates/plan-template.md ✅ aligned (tech stack section, project structure matches)
  - .specify/templates/spec-template.md ✅ aligned (no changes needed)
  - .specify/templates/tasks-template.md ✅ aligned (path conventions match, TDD emphasis present)
  - CLAUDE.md ✅ aligned (behavioral guidelines consistent with principles)
  
  Follow-up TODOs: None
-->

# 北京儒泰分销管理系统 Constitution

## Core Principles

### I. Test-Driven Development (TDD) — NON-NEGOTIABLE

All production code MUST be written following the TDD cycle strictly:

1. **Write a failing test** that defines the expected behavior
2. **Run the test and confirm it fails** (Red phase)
3. **Write the minimum code** to make the test pass (Green phase)
4. **Refactor** while keeping tests green (Refactor phase)

- Tests MUST be written before the corresponding implementation code — no exceptions
- Every API endpoint MUST have contract tests verifying request/response contracts
- Every business logic module MUST have unit tests covering happy path, edge cases, and error conditions
- Integration tests MUST cover the full user journeys defined in the specification
- Tests MUST be runnable with a single command — no manual setup required

**Rationale**: TDD ensures every line of code has a verified purpose, prevents regression, and serves as living documentation of expected system behavior. In a multi-developer, multi-system integration project, tests are the safety net that allows confident iteration.

### II. API-First Design

The backend REST API is the single source of truth for all business data and logic:

- Frontend applications (Vue admin, WeChat mini-program) MUST only consume backend APIs — never access the database directly
- API contracts (request/response schemas, error codes) MUST be defined and reviewed before implementation
- All APIs MUST follow the unified response format: `{code, message, data, requestId, serverTime}`
- API versioning MUST be URL-path-based (`/api/v1/...`) with backward-compatible changes within a major version
- Breaking changes require a new API version and migration plan

**Rationale**: Clear API boundaries enable independent development and testing of frontend and backend. The mini-program frontend already exists — the API must serve it reliably without coupling to implementation details.

### III. Separation of Concerns

The system consists of three independently deployable tiers:

| Tier | Location | Technology | Role |
|------|----------|------------|------|
| Backend API | `backend/` | Python | Business logic, data access, external integration |
| Admin Frontend | `manageSystem/` | Vue 3 + Vite | Management console for administrators |
| Mini-Program Frontend | `miniProgram/` | WeChat Mini-Program | End-user and promoter mobile experience |

- Each tier MUST be independently buildable and testable
- The backend MUST NOT contain frontend rendering logic
- The admin frontend and mini-program frontend MUST NOT contain business logic beyond presentation and form validation
- Cross-cutting concerns (authentication, logging, error handling) MUST be centralized in the backend

**Rationale**: Independent tiers allow parallel development, simplify testing, and enable different deployment cadences. The mini-program frontend is already built — backend and admin must integrate without modifying its core logic.

### IV. Database Integrity

All persistent data is stored in MySQL on Tencent Cloud, accessed exclusively through the backend API layer:

- The database connection MUST be configured via environment variables — never hardcoded
- All database schema changes MUST be managed through versioned migration scripts
- Sensitive data (phone numbers, ID cards, medical account numbers) MUST be encrypted at rest
- Audit logs MUST be written for all sensitive data access and modifications
- The database connection MUST use TLS for data in transit
- No client application (mini-program, admin SPA, third-party) may connect directly to the database

**Rationale**: Centralized data access through the backend ensures consistent validation, authorization, and audit logging. Direct database access from clients would bypass security controls and create data consistency risks.

### V. Simplicity (YAGNI)

You Aren't Gonna Need It — build only what is required now:

- No features beyond what the specification and PRD explicitly require
- No abstractions (repositories, factories, interfaces) for single-implementation code
- No "future-proofing" configurations or extension points without a concrete, near-term need
- Prefer straightforward, readable code over clever patterns
- If a module exceeds 200 lines, question whether it's doing too much
- External dependencies MUST be justified by concrete functionality — no "just in case" libraries

**Rationale**: Over-engineering creates maintenance burden, slows onboarding, and makes the codebase harder to reason about. In a project with clear, well-documented requirements, simplicity is a competitive advantage.

## Technology Stack

The following technology choices are binding for all development:

### Backend (`backend/`)
- **Language**: Python 3.11+
- **Framework**: FastAPI (REST API with auto-generated OpenAPI docs)
- **ORM**: SQLAlchemy 2.0+ with async support
- **Database**: MySQL 8.0 on Tencent Cloud (remote connection via TLS)
- **Testing**: pytest + pytest-asyncio (unit, integration, contract)
- **Migration**: Alembic (versioned schema management)
- **Validation**: Pydantic v2 (request/response schemas)
- **External Integration**: httpx (async HTTP client for Harbin Rutai API calls)
- **Scheduling**: APScheduler or Celery (for recurring tasks like `getBindUser` polling)

### Admin Frontend (`admin/`)
- **Framework**: Vue 3 (Composition API)
- **Build Tool**: Vite
- **UI Library**: Element Plus or Naive UI
- **State Management**: Pinia
- **HTTP Client**: Axios
- **Testing**: Vitest + Vue Test Utils

### Infrastructure
- **Cloud Database**: Tencent Cloud MySQL 8.0
- **File Storage**: Tencent Cloud COS (for qualification files, avatars, images)
- **Deployment**: Docker containers on Linux server
- **CI/CD**: Automated test execution on every push

## Development Workflow

### Task Execution Order

1. **Specification** (`/speckit-specify`) — Define what to build
2. **Planning** (`/speckit-plan`) — Design how to build it
3. **Task Generation** (`/speckit-tasks`) — Break into implementable units
4. **Implementation** (`/speckit-implement`) — Build following TDD

### Code Quality Gates

- All tests MUST pass before code is considered complete
- New code without tests MUST NOT be merged
- Test coverage on new code SHOULD exceed 80%
- Linting and formatting MUST be configured and enforced at the project level
- Pull requests MUST include a summary of what changed and why

### Commit Convention

- Commits SHOULD be atomic — one logical change per commit
- Commit messages SHOULD describe what changed and why (not how)
- Each user story phase SHOULD result in at least one checkpoint commit

### Environment Configuration

- All environment-specific values (database URL, API keys, secrets) MUST use environment variables
- A `.env.example` file MUST document all required variables with descriptions
- `.env` files MUST be in `.gitignore` — never committed

## Governance

This constitution supersedes all other development practices and guidelines. When a conflict arises between this constitution and any other document, this constitution takes precedence.

### Amendment Process

- Amendments require a clear rationale documented in the Sync Impact Report
- Principle removals or redefinitions constitute a MAJOR version bump
- New principles or materially expanded guidance constitute a MINOR version bump
- Clarifications, wording fixes, or typo corrections constitute a PATCH version bump
- All amendments MUST be reflected in the Sync Impact Report at the top of this file

### Compliance

- Every implementation plan (`plan.md`) MUST include a Constitution Check section that verifies alignment with each principle
- Code reviews MUST verify TDD compliance (tests written first, tests pass)
- Complexity that violates Principle V (Simplicity) MUST be explicitly justified in the plan's Complexity Tracking table

### Runtime Guidance

- `CLAUDE.md` provides behavioral guidelines for AI-assisted development
- When the constitution is silent on a topic, `CLAUDE.md` guidance applies
- Project-specific conventions not covered here SHOULD be documented in `CLAUDE.md`

**Version**: 1.0.0 | **Ratified**: 2026-07-30 | **Last Amended**: 2026-07-30
