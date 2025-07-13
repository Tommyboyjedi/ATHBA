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

### Current Challenge: Session Management

This strict decoupling introduces a significant challenge for managing session state. The standard and most secure way to interact with Django's session is via the `request.session` dictionary, which is only available on the `request` object.

The current implementation in `core/agents/agent_generator.py` works around this by manually decoding the `session_key` string to extract session data.

**Identified Risks with the current approach:**

1.  **Fragility:** The format of the session key is an internal Django implementation detail and is not guaranteed to remain stable across different Django versions. This makes the implementation brittle and prone to breaking during upgrades.
2.  **Security:** This method bypasses Django's built-in session security, specifically the cryptographic signature that prevents tampering.

This design choice represents a trade-off: it achieves high decoupling at the cost of relying on a fragile and less secure mechanism for session data access. Future work should address this trade-off.

## 2. General Coding Philosophy

### Guiding Principles

The overarching goal is to produce well-structured, maintainable, and object-oriented code. The following principles guide development:

1.  **Prioritize Debuggability:** The most important consideration when writing code is that it should be easy to debug. This means favoring clarity, straightforward logic, and avoiding overly complex or "magical" implementations that obscure the flow of execution.

2.  **Pragmatic Application of SOLID:** The SOLID principles of object-oriented design are highly valued and serve as a strong guide for architectural decisions. However, they are not to be followed dogmatically. There is a preference for pragmatism over purism, and principles may be bent when it leads to a simpler, more maintainable, or more debuggable outcome.
