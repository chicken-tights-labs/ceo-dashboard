---
name: Story
about: A user story with Gherkin acceptance criteria
title: 'US-DASH-00N: '
labels: ['needs-review']
assignees: []
---

## Story

<!-- What story does this implement? -->

## Gherkin Acceptance Criteria

```gherkin
Feature: <feature name>
  As a <role>
  I want <goal>
  So that <benefit>

  @cursor
  Scenario: <scenario name>
    Given <context>
    When <action>
    Then <expected outcome>
```

## Out of Scope

<!-- What is explicitly NOT included in this story? -->

## How to Verify

<!-- Manual or automated check -->

## Docs to Update

<!-- Which doc(s) need updating: Obsidian notes, inline README, architecture.md, etc. -->

## Open Questions

<!-- Anything blocking implementation -->

---

> **Note on auto-ticketing**: The auto-ticket creator scans `tasks/requirements.md` for `@cursor` scenarios — it does **not** read GitHub issues. To auto-generate a kanban ticket, write the Gherkin in `tasks/requirements.md` (the script now supports `@cursor` tags before `Scenario:`, matching this template's format). GitHub issues created from this template track work manually.
