# Tree-sitter UI Design Contract

## Design thesis

Tree-sitter is one compact operational console inside Agent Zero. Runtime truth, repository limits, structural-context controls, inspection tools, and output belong to one continuous surface with crisp one-pixel divisions. The interface must feel native to Agent Zero, not like a separate dashboard.

Automatic structural context is the primary product experience: when enabled, it grounds the first model call for active-project work and can incrementally refresh changed files. **Code Intelligence is a secondary, manual diagnostic surface** for deeper context assembly, definition lookup, file parsing, structural queries, index checks, and raw result inspection. Do not make the Inspector look like the normal prerequisite for receiving structural context.

## Tokens and color

Use Agent Zero tokens for the base world: `--color-background`, `--color-panel`, `--color-input`, `--color-border`, `--color-text`, `--color-text-muted`, and the host warning color. Use the existing Agent Zero `.btn`, `.btn-primary`, `.toggle`, and `x-icon` treatments rather than restyling equivalent controls from scratch. Results use `--font-family-monospace`.

Tree-sitter adds only a restrained mint semantic accent:

| Token | Dark value | Light value | Use |
| --- | --- | --- | --- |
| `--ts-accent` / `--ci-accent` | `#78d6b2` | `#147a5b` | Ready state, active result tab, key Tree-sitter icons, selection |
| `--ts-accent-strong` / `--ci-accent-strong` | `#3dbf91` | `#16805f` | Focus rings and enabled toggles |
| `--ts-accent-soft` / `--ci-accent-soft` | Accent at 12% over transparent | Same formula | Quiet icon and readiness backgrounds |

Mint means Tree-sitter identity or positive runtime readiness. It is not a general decoration color. Missing, setup-required, unavailable, and inline-error states use the host warning treatment. Disabled controls reduce opacity to `0.42` and must not imply availability.

## Typography

Inherit Agent Zero's interface typeface. The hierarchy is compact and weight-led:

- Inspector title: `1.25rem`, tight `1.18` line height, `-0.02em` tracking.
- Settings runtime title: about `1.02rem`; section and workbench headings: `0.88–0.9375rem`.
- Runtime values: `0.92rem`, bold, with tabular numerals.
- Descriptions, labels, controls, status pills, and tabs: approximately `0.68–0.79rem`, using muted color for supporting copy.
- Structured output: `0.75rem` monospace at `1.55` line height, wrapped safely for long data.

Use sentence case. Do not introduce uppercase eyebrow labels. Hierarchy comes from placement, weight, spacing, and dividers—not ornamental microcopy.

## Continuous-console composition

Settings are enclosed by one `14px`-radius panel. The reading order is runtime header, four runtime facts, two configuration groups, then repository boundary and the Code Intelligence action. On desktop, facts form four equal columns and the two configuration groups share a balanced two-column row. The boundary is the console footer, not another card.

The Inspector is a continuous workbench up to `1120px` wide: title/runtime header, repository command bar, paired task/file tools, then the result dock. The two tools use a slightly narrower context column and wider inspection column (`0.92fr / 1.08fr`) to reflect their field density.

Use one-pixel `--color-border` rules to describe structure:

- horizontal rules separate major console bands;
- vertical rules separate peer columns and runtime facts on wide screens;
- toggle rows receive top rules within their group;
- when columns stack, replace the vertical rule with a horizontal rule;
- do not wrap each fact, field, toggle, or workflow in its own floating card.

## Runtime and state patterns

Runtime status is always near the surface title and announced through `aria-live="polite"`. The pill combines text with a small colored dot and supports explicit checking, ready, setup-required/unavailable states. Settings also expose language-pack version, available-language count, cached-parser count, and automatic/manual integration as plain runtime facts.

Loading facts use a quiet four-part skeleton. If runtime lookup fails, keep saved settings usable and show the compact explanatory error. Inspector operation errors appear as an inline `role="alert"` band. Busy actions change to direct progressive labels such as “Indexing…”, “Building…”, and “Inspecting…”. Actions remain disabled until their required repository, task, symbol, or file input exists.

## Fields, toggles, and actions

Fields use visible semantic labels, compact `8px`-radius Agent Zero inputs, descriptive examples, and tabular numerals for numeric settings. Optional inputs say “optional” next to the field name. Place related numeric controls in two columns where width allows; allow the definition-snippet limit to span the settings group.

Toggles are full-row labels with a concise bold name and, where useful, one muted sentence explaining the consequence. The toggle stays left of its copy. Keep automatic context and incremental refresh together; keep untracked and hidden-file indexing together. Treat outside-project access as a distinct repository-boundary decision, off unless explicitly enabled.

Primary buttons name the operation: “Open Code Intelligence,” “Refresh index,” “Build context,” and “Inspect file.” Secondary actions include “Find definitions,” index-status inspection, copy, and clear. Icon-only controls require both an accessible label and a tooltip/title. On narrow screens, primary workflow buttons expand to the available width.

## Inspector result dock

Results appear below the tools as a docked continuation of the workbench, never as a detached modal or card. Keep the most recent outputs available so users can compare operations. The dock contains a result heading, “Copy JSON,” clear, visible tabs only for available result types, and a scrollable JSON pane capped at `25rem` high.

The active tab is indicated by mint text and a `2px` bottom rule and exposes `aria-current="page"`. Tabs scroll horizontally instead of compressing or wrapping. The JSON pane is keyboard-focusable, uses the host monospace token, preserves readable whitespace, wraps long content, and allows internal scrolling.

## Responsive behavior

- Settings at `760px` and below: stack the runtime header, convert facts to a two-by-two grid, stack configuration groups and the boundary, and make “Open Code Intelligence” full width.
- Settings at `430px` and below: collapse numeric field grids to one column.
- Inspector at `820px` and below: move the repository label above its input/actions, stack the two tools, and convert their vertical divider to a horizontal divider.
- Inspector at `560px` and below: stack title and runtime status, make the repository a single column, stack tool field rows and workflow actions, expand primary actions, and reduce “Copy JSON” to its labeled icon affordance while retaining its accessible name.

Preserve the host modal's scrolling and sticky action behavior. Narrow layouts must remain usable at browser zoom without horizontal page overflow.

## Accessibility and motion

Use semantic headings, sections, labels, description lists, navigation, and buttons. Decorative icons are hidden from assistive technology; icon-only controls have explicit labels. Preserve native keyboard operation and expose a visible `2px` Tree-sitter accent focus ring with `2px` offset on fields, toggles, buttons, and the result pane. Keep status updates polite and errors assertive. Maintain sufficient contrast in both Agent Zero themes.

Surface entry motion is a short `240ms` fade with only `4–5px` vertical travel. Toggle transitions are `150ms`. Under `prefers-reduced-motion: reduce`, remove entry animation and toggle transitions. Do not add looping, decorative, or attention-seeking motion.

## Copy voice

Copy is direct, technical, compact, and truthful. Name what the control does and state its boundary or consequence in one sentence. Prefer “Runtime ready,” “Setup required,” “Refresh changed files,” and “Inspection stays inside the active project” over promotional language. Structural references and clean syntax must never be described as proof of type resolution, compilation, or behavioral correctness.

Use Agent Zero, Tree-sitter, and Code Intelligence consistently. Do not add testimonials, benchmarks, inflated claims, or manual installation/repair language; dependency provisioning and validation are automatic lifecycle behavior.

## Anti-regression rules

- Do not replace the continuous console with disconnected, same-size card grids.
- Do not add eyebrow labels, decorative numbering, step badges, or ornamental section captions.
- Do not position the manual Inspector as the primary workflow; automatic structural context remains primary.
- Do not hide runtime truth or collapse checking, ready, setup-required, and unavailable into one ambiguous state.
- Do not imply that syntax inspection proves compiler, type, or behavioral correctness.
- Do not weaken the active-project boundary or visually normalize outside-project access.
- Do not invent a competing color, typography, button, toggle, modal, or elevation system outside Agent Zero tokens.
- Do not use mint for neutral decoration or warnings.
- Do not detach results from their originating workbench or discard prior operation tabs when comparable results exist.
- Do not remove semantic labels, visible focus, reduced-motion handling, responsive stacking, or keyboard access to results.
