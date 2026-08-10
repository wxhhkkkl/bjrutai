<!-- SPECKIT START -->
Current Spec Kit feature:

- Plan: `../specs/014-article-reading/plan.md`
- Specification: `../specs/014-article-reading/spec.md`
- Tasks: `../specs/014-article-reading/tasks.md`
- Project constitution: `.specify/memory/constitution.md`

Read the constitution and current feature artifacts before implementing work.
Use the confirmed UI files under `../UI设计稿已确认/` as the visual contract.
<!-- SPECKIT END -->

# LuTaiPage AI Development Rules

These rules apply to every AI coding agent working in `LuTaiPage/`. They
supplement the Spec Kit artifacts above and do not replace the project
constitution.

## 1. Instruction Priority

When instructions conflict, follow this order:

1. The user's latest explicit request.
2. `.specify/memory/constitution.md`.
3. The active feature's `spec.md`, `plan.md`, `tasks.md`, and contracts.
4. Confirmed designs in `../UI设计稿已确认/` and recorded design amendments.
5. This file and the existing codebase conventions.

Do not silently resolve a conflict between the PRD, specification, flow,
confirmed design, and code. Record the conflict in the feature specification or
ask the product owner when it changes scope, privacy, security, data semantics,
or an irreversible user action.

## 2. Think Before Coding

Before editing code:

- Read the files that own the behavior and inspect nearby patterns.
- State material assumptions when the repository does not answer them.
- Translate the request into a small, verifiable outcome.
- For multi-step work, give a brief plan with a verification check per step.
- Identify affected routes, roles, UI states, data fields, privacy rules, and
  external mini-program dependencies.

Ask before proceeding only when ambiguity materially affects scope, security,
privacy, product rules, data loss, or irreversible actions. For low-risk
implementation details, choose the simplest option consistent with the project,
state the assumption, and continue.

## 3. Specification and Task Discipline

- Do not implement behavior that is absent from the active specification or its
  acceptance scenarios.
- Keep implementation traceable to a requirement, user story, or task ID.
- If the requested behavior changes scope, update the Spec Kit artifacts before
  code.
- Work in task priority order and complete one independently verifiable slice at
  a time.
- Use mock data for the first demonstrable version unless the active plan
  explicitly schedules backend integration.

Small fixes may update an existing task instead of creating speculative process
documents, but they must still respect the constitution and confirmed UI.

## 4. Simplicity First

Write the minimum code that fully satisfies the specified behavior.

- Do not add unrequested features, configuration, dependencies, or frameworks.
- Application source uses JavaScript. Do not introduce TypeScript, Taro,
  uni-app, React, Vue, or another cross-platform application framework.
- Do not create an abstraction for a single use unless it removes real
  complexity or matches an established project pattern.
- Prefer native WeChat Mini Program APIs, WXML, WXSS, JavaScript, Skyline, and
  existing components.
- Vant Weapp (`@vant/weapp`) is the only pre-approved third-party UI library.
  Introduce it only when the active plan names the required components; pin its
  version, register components on demand, and document the npm build step.
- Prefer clear page-local code until reuse is demonstrated.
- Treat line-count limits as review signals, not hard rules. If a solution is
  much larger than the behavior requires, simplify it.
- Do not build speculative infrastructure for future API, role, or page needs.

## 5. Surgical Changes

Every changed line must be explainable by the current request.

- Touch only the files required by the active task.
- Match existing naming, formatting, component, and state-management patterns.
- Do not reformat, rename, refactor, or delete unrelated code.
- Do not overwrite or revert user changes already present in the worktree.
- Remove imports, variables, styles, routes, and helpers made unused by your own
  change.
- Mention unrelated defects or dead code separately; do not fix them unless
  requested or required for correctness.

## 6. UI Implementation Rules

- Build approved screens with real WXML/WXSS and reusable components, never with
  a screenshot as the interactive page.
- Bottom Tab pages are 首页、客户、贡献、我的 and must not contain a duplicate
  page-level back/title navigation bar.
- Secondary pages must account for the WeChat status bar, fixed menu capsule,
  safe areas, and keyboard behavior.
- Business icon containers must be true 1:1 rounded squares; do not stretch
  source icons.
- Follow the approved global action hierarchy: one black primary capsule action
  per page, with restrained secondary actions.
- Vant components are implementation helpers, not the visual specification.
  Override their tokens or styles as needed to match the confirmed design, and
  use native or project components when Vant would make that match harder.
- Preserve the information hierarchy, spacing, color, typography, radius, and
  state variants shown in the confirmed design.
- Do not invent content or states to fill visual space. Missing content belongs
  in a defined loading, empty, error, pending, or no-permission state.

## 7. Data, Privacy, and Failure Handling

- Never commit real customer data, medical data, credentials, tokens, app
  secrets, or production identifiers.
- Mask sensitive fields by default and keep sensitive values out of logs,
  analytics, screenshots, fixtures, and error messages.
- Handle realistic boundary failures: network, timeout, malformed response,
  permission denial, expired login, invalid user input, stale data, external
  mini-program failure, and duplicate submission.
- Do not add defensive branches for states prohibited by a validated local
  invariant unless an external boundary can violate that invariant.
- Preserve binding semantics: `hrb_user_id: null` means pending match, not
  terminal failure.
- Side-effecting requests must prevent duplicate submission and follow specified
  idempotency and retry rules.

## 8. Goal-Driven Verification

Define completion in observable terms and keep working until it is verified.

- Bug fix: reproduce the failure, implement the smallest fix, then verify the
  original path and the regression path.
- New behavior: verify every acceptance scenario and required state variant.
- Refactor: show behavior is unchanged before and after.
- UI work: verify representative iOS and Android WeChat viewports, safe areas,
  text overflow, touch targets, loading/empty/error states, and navigation.
- Shared logic: add focused automated tests where practical.
- Run the narrowest relevant checks first, then the broader project checks
  required by the active plan.

Do not report work as complete while required checks are failing. If a check
cannot be run, report exactly what was not verified and why.

## 9. Completion Report

At the end of a coding task, report:

- what changed and which requirement or task it satisfies;
- the files changed;
- checks run and their results;
- remaining risks, blocked checks, or follow-up decisions.

Keep the report concise. Do not claim unrun tests, visual checks, backend
integration, or device behavior as verified.
