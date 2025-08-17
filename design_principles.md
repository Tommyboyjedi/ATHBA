# Project Design Principles

This document outlines key design principles and architectural decisions made for the ATHBA project. It serves as a guide to understand the rationale behind the system's structure, especially in cases where the implementation might differ from standard practices.

## 1. Agent Decoupling from the Web Framework

### Principle

A core design principle of this project is the **strict separation of Agent components from the web framework (Django)**. Agents are considered pure business logic components and must remain completely independent of the web request-response cycle.

### Justification

This decoupling is intentional and provides several key benefits:

*   **Testability:** Agents can be tested in isolation without needing to mock or construct complex Django `HttpRequest` objects. This simplifies unit testing and improves reliability.
*   **Portability:** The agent logic is not tied to Django. This allows agents to be reused in different contexts, such as a command-line interface, a different web framework, or a background worker process, with minimal to no modification.
*   **Separation of Concerns:** It enforces a clean architecture where the web layer is responsible for handling web-specific tasks (like HTTP parsing and session management), and the agent layer is focused exclusively on its business logic.

### Implementation Constraints

To enforce this principle, the following constraint must be observed:

*   The Django `HttpRequest` object **must not** be passed beyond the service layer (e.g., `ChatService`).
*   Agents and their associated components (like `AgentGenerator` or `AgentBehavior`) must not import from `django.http` or have any direct knowledge of the request object.

### Session Management (Updated Policy)

This strict decoupling impacts how we manage session state. The authoritative and secure way to access session data is via `request.session`, which exists only on the Django request object.

Updated rules we follow:

1. Endpoints and services that need session data must receive the `request` and access `request.session` directly.
2. Agents must never parse or decode `session_key`. Agents receive a lightweight, immutable session struct (`Projses`) created by services and, where needed, an adapter such as `SessionProxy` to perform session-safe operations on their behalf.
3. The boundary is enforced in `ChatService` (and similar services): it reads from `request.session`, then constructs `Projses` and passes it into agents via `AgentGenerator`.

This preserves security and stability while keeping agents framework-agnostic.

## 2. General Coding Philosophy

### Guiding Principles

The overarching goal is to produce well-structured, maintainable, and object-oriented code. The following principles guide development:

1.  **Prioritize Debuggability:** The most important consideration when writing code is that it should be easy to debug. This means favoring clarity, straightforward logic, and avoiding overly complex or "magical" implementations that obscure the flow of execution.

2.  **Pragmatic Application of SOLID:** The SOLID principles of object-oriented design are highly valued and serve as a strong guide for architectural decisions. However, they are not to be followed dogmatically. There is a preference for pragmatism over purism, and principles may be bent when it leads to a simpler, more maintainable, or more debuggable outcome.

## 3. Agent System Direction (Summary)

- **Multi-intent per turn:** A single user message may produce multiple intent objects (e.g., several spec updates and questions simultaneously). Behaviors consume each item independently.
- **AI-first extraction:** No keyword heuristics in behaviors. The LLM must populate entities (e.g., `humanIdeas`, `specSections`) even when asking questions. Schema validation and a repair pass ensure reliability.
- **Toward always-on:** We will evolve to a background scheduler and job queue for autonomous agents that continue work beyond a single HTTP turn (see `docs/ARCHITECTURE.md`).
