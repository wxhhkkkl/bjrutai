<!--
Sync Impact Report
- Version change: 1.0.0 -> 1.1.0
- Added principles:
  - I. Specification Before Implementation
  - II. Confirmed UI Is the Visual Contract
  - III. Privacy and Medical Scope Boundaries
  - IV. Explicit States and Resilient Flows
  - V. Testable, Incremental Delivery
  - VI. Native Mini Program Simplicity
- Added sections:
  - Technical and Product Constraints
  - Development Workflow and Quality Gates
- Removed sections: none; template placeholders were replaced.
- Templates:
  - .specify/templates/plan-template.md: updated
  - .specify/templates/spec-template.md: updated
  - .specify/templates/tasks-template.md: updated
- Active artifacts:
  - specs/001-four-tab-foundation/plan.md: updated
  - specs/001-four-tab-foundation/research.md: updated
- Deferred items: `@vant/weapp` installation and version pinning remain
  feature-scoped; the current feature does not require installation yet.
-->

# LuTaiPage Constitution

## Core Principles

### I. Specification Before Implementation

Every feature MUST begin with a Spec Kit specification that defines user value,
scope, acceptance scenarios, edge cases, privacy implications, and measurable
outcomes. Implementation MUST NOT begin until the specification is ready for
planning and its plan and tasks are traceable to requirements. The PRD, confirmed
UI inventory, and four-Tab flow document are project inputs; when they conflict,
the conflict MUST be resolved in the specification rather than guessed in code.

### II. Confirmed UI Is the Visual Contract

Files in `../UI设计稿已确认/` are the approved visual baseline. Pages MUST be
implemented as real WXML/WXSS components, never as screenshot backgrounds.
Reusable controls MUST follow the approved global rules: one black primary
capsule action per page, restrained secondary actions, true 1:1 rounded-square
business icon containers, consistent spacing, and touch targets of at least
44 points. Bottom Tab pages MUST NOT add a page-level back/title navigation bar;
secondary pages MUST respect the WeChat capsule and safe areas.

### III. Privacy and Medical Scope Boundaries

Customer data MUST be minimized, masked by default, and displayed only for an
authorized business purpose. Mobile numbers, identity numbers, medical-insurance
accounts, and family contact details MUST NOT be logged or rendered in full
without an explicit authorized flow. The Beijing mini program MUST NOT introduce
diagnosis, prescription, consultation, payment, or consumer medical profiling.
Unbinding and customer transfer remain administrator-only operations outside the
mini program.

### IV. Explicit States and Resilient Flows

Every network-backed feature MUST define loading, empty, success, recoverable
error, terminal error, and no-permission states where applicable. Binding states
MUST distinguish success, pending match, already bound, and retry processing.
`hrb_user_id: null` MUST be treated as pending match, not terminal failure.
Retries, idempotency, stale-data indicators, and user-safe recovery actions MUST
be specified before integration code is written.

### V. Testable, Incremental Delivery

User stories MUST be independently demonstrable with mock data before backend
integration. Shared utilities, routing, authorization, masking, and API contracts
MUST have automated tests where practical; every feature MUST include runnable
acceptance checks for its primary journey and state variants. Visual acceptance
MUST cover representative iOS and Android WeChat viewports, safe areas, text
overflow, and interactive hit areas. A story is not complete while its specified
acceptance scenarios fail.

### VI. Native Mini Program Simplicity

The current implementation target is a native WeChat mini program using
WXML/WXSS/JavaScript and Skyline. TypeScript and cross-platform application
frameworks MUST NOT be introduced without a constitutional amendment. Existing
project patterns and native platform capabilities MUST be preferred over new
frameworks or unnecessary dependencies. Vant Weapp (`@vant/weapp`) is the only
pre-approved third-party UI library and MAY be introduced when a feature plan
identifies specific components that reduce implementation or accessibility
risk. Its version MUST be pinned, components MUST be registered on demand, and
their appearance MUST conform to the confirmed UI rather than replacing it.
The production base-library version MUST be pinned to a stable release rather
than `trial`. Abstractions MUST solve demonstrated reuse or complexity;
speculative infrastructure is prohibited.

## Technical and Product Constraints

- The development root is `LuTaiPage/`.
- Application code uses JavaScript; new application source files MUST NOT use
  TypeScript.
- The application remains a native WeChat Mini Program; Taro, uni-app, React,
  Vue, and other cross-platform application frameworks are outside the approved
  stack.
- Vant Weapp is optional rather than mandatory. A feature that introduces it
  MUST record the selected components, pinned version, npm build steps, and
  impact on package size in its plan and tasks.
- The four primary navigation entries are 首页、客户、贡献、我的.
- Role recognition determines the home workbench: promoter, doctor, or
  qualification-review state.
- The Beijing mini program owns promotion, customer attribution, contribution
  display, qualification state, and compliant account functions.
- Harbin Rutai owns downstream medical-service experiences; cross-mini-program
  transitions MUST be represented as external dependencies.
- Interface contracts MUST document field names, masking rules, status values,
  pagination, error codes, retry behavior, and data freshness.
- Real customer or credential data MUST NOT be committed as fixtures.
- Confirmed UI changes require an updated specification or an explicitly
  recorded design amendment before implementation changes.

## Development Workflow and Quality Gates

1. Run `$speckit-specify` to create or update a feature specification.
2. Resolve material ambiguity with `$speckit-clarify` before planning.
3. Run `$speckit-plan`; the plan MUST pass the Constitution Check.
4. Run `$speckit-tasks`; every task MUST reference exact files and a requirement
   or user story.
5. Implement in priority order with mock-data acceptance before API integration.
6. Run `$speckit-analyze` after tasks and before implementation for shared or
   high-risk features.
7. Validate automated checks, WeChat Developer Tools compilation, navigation,
   privacy masking, and approved design states before marking work complete.

Code review MUST reject:

- behavior without a specification or acceptance scenario;
- hard-coded production personal data or credentials;
- screenshots used as interactive UI;
- new terminal states that contradict the PRD;
- Tab pages that reintroduce page-level navigation;
- unhandled loading, empty, error, or permission states required by the spec.

## Governance

This constitution supersedes informal implementation habits. Amendments require:

1. a documented reason and affected features;
2. a semantic-version change;
3. updates to dependent Spec Kit templates and active plans;
4. approval from the product/design owner when product or UI rules change.

MAJOR versions remove or redefine governing principles. MINOR versions add or
materially expand principles. PATCH versions clarify wording without changing
obligations. Every feature plan and review MUST record constitution compliance.

**Version**: 1.1.0 | **Ratified**: 2026-07-27 | **Last Amended**: 2026-07-27
