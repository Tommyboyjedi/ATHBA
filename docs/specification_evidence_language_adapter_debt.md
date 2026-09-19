# Specification evidence language-adapter debt

ATHBA's core remains intended to be language agnostic:

ATHBA generic evidence policy -> language-specific evidence adapter ->
deterministic language/tooling analysis.

Core policy owns the requested obligation, modality, canonical revision binding,
evidence status and retained findings. Language adapters own syntax, imports,
effects analysis and the supported deterministic tooling for that language.

Current deterministic specification evidence is implemented primarily through
the Python language adapter. Python AST classifications, decorator handling,
standard-library rules and storage API names are Python implementation details.
They must not become generic ATHBA semantics or be applied to other languages
merely because the core exposes the same evidence policy.

Future work must provide equivalent language-specific evidence capabilities for
at least:

- Python (continued assurance/coverage improvements)
- Rust
- JavaScript
- TypeScript
- HTML
- CSS
- C#
- Java
- PowerShell

Each adapter must state which evidence policies its language/tooling can support,
retain deterministic analysis limits and warnings, distinguish detected violations
from blocking unknowns and explicitly accepted assurance limitations, and bind
results to the inspected revision. Capabilities may be inapplicable for some
languages; that must be declared rather than simulated by Python rules.

No additional language adapter is implemented in PR30. This is recorded
architectural debt, not authorization for multi-language implementation or
a redesign of Gatekeeper, behavior planning, TDD, or Rack AI.
