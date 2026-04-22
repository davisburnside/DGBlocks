# DGBlocks Memory Bank

This Memory Bank maintains context across sessions for the DGBlocks addon template. It contains documentation about the project's architecture, patterns, and current state.

## Memory Bank Files

| File | Purpose |
|------|---------|
| [projectBrief.md](./projectBrief.md) | Core goals and "why" of the project |
| [productContext.md](./productContext.md) | How it works, user experience goals, and target problems |
| [systemPatterns.md](./systemPatterns.md) | Technical architecture, design patterns, and code structure |
| [techContext.md](./techContext.md) | Technologies used, dependencies, and development setup |
| [progress.md](./progress.md) | What is built, what is left, and current status |
| [activeContext.md](./activeContext.md) | Tracks what we are working on "right now" |

## Block Documentation

Each block, either natively included or cloned from git, should have its own README file.
It should explain the block's purpose, architecture, dependencies, integration points, and any deviations from the standard block format

## Memory Bank Usage

This Memory Bank serves multiple purposes:

1. **Onboarding**: Helps new developers understand the system
2. **Context Retention**: Maintains information across development sessions
3. **Documentation**: Provides a centralized location for design decisions and patterns
4. **Progress Tracking**: Documents what has been built and what remains


# What to Update (and When)
You don't need to update everything every time you fix a typo, but you should instruct the AI Assistant to update specific files during these key moments:

## 1. projectbrief.md (The "North Star")
Update when: Your core goals or project scope changes.

Focus: If you decide to pivot from a local-only tool to a cloud-synced one, or if you add a major new "pillar" to the project, update this immediately. It prevents the AI Assistant from suggesting features that are out of scope.

## 2. productContext.md (The "Why")
Update when: You change how a user interacts with the tool or its intended "vibe."

Focus: Changes in UX flow, target audience needs, or the "problems" the software is solving.

## 3. systemPatterns.md (The "How" - High Priority)
Update when: You introduce a new design pattern, library, or architectural decision.

Focus: * New Tech: If you just added a library like Numba or specialized Blender UI logic.

Communication: How data flows between your UI and the backend/operators.

Rules: Specific coding standards (e.g., "Always use bmesh for mesh operations instead of bpy.ops").

## 4. techContext.md (The Stack)
Update when: You add or remove dependencies.

Focus: Version updates, new external API integrations, or changes in the development environment requirements.

## 5. activeContext.md (The "Now" - Update Daily)
Update when: You finish a session or start a new major task.

Focus: What was just completed, what the current "headache" is, and what the next three logical steps are. This is the most "living" part of the bank.

## 6. progress.md (The Checklist)
Update when: A feature goes from "In Progress" to "Done."

Focus: Keeping an accurate roadmap so the AI Assistant doesn't try to "re-build" something that is already 90% finished.