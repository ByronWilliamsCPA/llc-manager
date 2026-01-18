# Project Vision & Scope: LLC Manager

> **Status**: Active | **Version**: 1.0 | **Updated**: 2026-01-18

## TL;DR

LLC Manager is a web application for a small family office to centralize LLC entity information, replacing fragmented Excel spreadsheets with a searchable, role-based dashboard that tracks compliance dates, ownership structures, and entity documentation.

## Problem Statement

### Pain Point

Managing 15-25 LLC entities across a family office using disparate Excel spreadsheets leads to:

- Missed compliance deadlines (registered agent renewals, state registration renewals, tax filings)
- Difficulty answering quick questions about entity details (EIN, formation state, ownership percentages)
- No single source of truth for entity relationships and document locations
- Manual effort to cross-reference information across multiple files

### Target Users

- **Primary**: Family office administrators (3-5 users) who manage day-to-day LLC operations
- **Secondary**: Family members and advisors (5-10 users) who need read access to entity information
- **Context**: Desktop web access behind Traefik/Pangolin reverse proxy, authenticated via Authentik SSO

### Success Metrics

| Metric | Current State | Target |
|--------|---------------|--------|
| Time to answer entity question | 5-15 minutes (find spreadsheet, locate data) | < 30 seconds |
| Missed compliance deadlines | 2-3 per year | 0 with 30-day advance notifications |
| Data freshness | Updated quarterly | Real-time with edit history |
| Document access | Manual file system navigation | 2 clicks from entity detail |

## Solution Overview

### Core Value

A unified web dashboard that consolidates all LLC entity data into a searchable, notification-enabled interface with role-based access control.

### Key Capabilities (MVP)

1. **Entity Dashboard**: Centralized view of all LLCs with key details (legal name, EIN, formation state) and quick-filter capabilities
2. **Compliance Calendar**: Dashboard showing upcoming deadlines (RA renewals, state filings, tax dates) with Apprise notifications
3. **Entity Detail View**: Comprehensive single-entity view with ownership, bank accounts, state registrations, and linked documents
4. **Relationship Visualization**: Display parent-child entity relationships for complex structures

## Scope Definition

### In Scope (Phase 1 MVP)

- ✅ **Entity CRUD**: Create, read, update entities with all core fields (legal name, DBAs, EIN, addresses, etc.)
- ✅ **Ownership Tracking**: Record owners with ownership percentages and types
- ✅ **State Registrations**: Track states where registered, registration dates, renewal dates
- ✅ **Registered Agents**: Store RA information with renewal date tracking
- ✅ **Bank Accounts**: Record bank account details per entity
- ✅ **Tax Filing Dates**: Track federal/state tax due dates and filing status
- ✅ **Document Links**: Store document metadata and file paths (served via HTTP endpoint)
- ✅ **Edit History**: Track who changed what and when (updated_at, updated_by fields)
- ✅ **Compliance Dashboard**: Visual calendar of upcoming deadlines
- ✅ **Search & Filter**: Full-text search across entity names, EINs, addresses
- ✅ **Authentik SSO**: OAuth2/OIDC integration for authentication
- ✅ **Role-Based Access**: Admin (full CRUD) vs Viewer (read-only) roles
- ✅ **Apprise Notifications**: Configurable alerts for approaching deadlines
- ✅ **Docker Deployment**: Single container deployable to Portainer from GitHub

### Out of Scope

- ❌ **Activity Management**: Day-to-day LLC operations, transactions, accounting
- ❌ **Document Storage**: Physical file storage (use existing file server/SharePoint)
- ❌ **Automated Filings**: Integration with state filing systems
- ❌ **Financial Reporting**: Balance sheets, P&L, financial analytics
- 🔄 **LLM Q&A Interface**: Natural language queries about entities (Phase 2)
- 🔄 **PDF Ingestion**: Automatic extraction from LLC documents (Phase 2)
- 🔄 **Vector Search**: Semantic search across ingested documents (Phase 2)

## Constraints

### Technical

- **Platform**: Web application (FastAPI backend, modern frontend)
- **Language**: Python 3.12
- **Database**: PostgreSQL (existing infrastructure)
- **Authentication**: Authentik OIDC (existing infrastructure)
- **Deployment**: Docker container via Portainer, GitHub Container Registry
- **Network**: Behind Traefik reverse proxy (Pangolin front-end)
- **Performance**: Dashboard load < 2s, search results < 500ms

### Business

- **User Base**: 5-15 concurrent users maximum
- **Data Volume**: 15-25 entities with ~50 related records each
- **Availability**: Standard business hours; maintenance windows acceptable
- **Compliance**: Internal family office use only; no external regulatory requirements

## Assumptions to Validate

- [ ] Authentik instance supports OIDC with group claims for role-based access
- [ ] Apprise instance is accessible from Docker network for notification delivery
- [ ] PostgreSQL database is provisioned and accessible
- [ ] Document file paths reference accessible network storage
- [ ] GitHub Container Registry is configured for Portainer pulls

## Related Documents

- [Architecture Decisions](./adr/)
- [Technical Spec](./tech-spec.md)
- [Roadmap](./roadmap.md)
