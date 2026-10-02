# CEO Dashboard

A lightweight, visual workflow system for tracking Salesforce development work — bridging Obsidian requirements, Hermes Kanban, and Cursor development.

## Features
- **Static Kanban Mirror**: Hourly exports of board status to markdown
- **Auto-Ticket Creator**: Gherkin stories in Obsidian → Kanban tickets
- **Live Dashboard UI**: Web interface at hermes.chickentightslabs.com/ceo-dashboard

## Structure
```
ceo-dashboard/
├── README.md          # You are here
├── tasks/
│   ├── requirements.md # Gherkin user stories
│   ├── architecture.md # Technical design
│   └── backlog.md      # Auto-synced kanban list
└── src/               # Dashboard source code
```

## Workflow
1. Write Gherkin stories in `tasks/requirements.md`
2. Tag with `@cursor` for AI development assignment
3. Hermes converts to GitHub issue + Kanban ticket
4. Cursor implements on a feature branch
5. PR review → merge to main

## Live URLs
- [GitHub Repo](https://github.com/chicken-tights-labs/ceo-dashboard)
- [Dashboard UI](https://hermes.chickentightslabs.com/ceo-dashboard)
