# Dashboard Requirements - Gherkin Stories

## Feature: Static Kanban Mirror
As a project manager
I want hourly exports of kanban status to markdown
So that I can see all active work in Obsidian

### Scenario: Export current board state
```gherkin
Given the kanban board has active tickets
When the hourly cron job runs
Then a markdown table is written to "Obsidian Vault/Active Projects/Kanban Mirror.md"
And the file shows ticket ID, title, status, and assignee
```

## Feature: Auto-Ticket Creator @cursor
As a requirements author
I want Gherkin stories in Obsidian to automatically become kanban tickets
So that I don't have to manually enter tickets

### Scenario: New requirement triggers ticket creation
When the file contains Gherkin scenarios tagged with @cursor
Then a new kanban ticket is created with:
  | Field  | Value          |
  | Title  | <scenario name>          |
  | Body   | <full Gherkin content>   |
  | Labels | platform:cursor,needs-review |
  | Status | ready                    |

## Feature: Dashboard UI
As a CEO/project owner
I want a live web dashboard showing kanban status
So that I can monitor progress at a glance

### Scenario: View live board status
```gherkin
When I navigate to https://hermes.chickentightslabs.com/ceo-dashboard
Then I see a color-coded table of active tickets
And tickets are grouped by epic
And AI-assigned tickets show green, human-reviews show blue
```
