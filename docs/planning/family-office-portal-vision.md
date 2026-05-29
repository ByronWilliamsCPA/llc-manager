# Family Office Estate Portal -- Project Vision

> **Document type:** Project Vision Statement
> **Prepared for:** Design Team
> **Date:** 2026-05-06
> **Status:** Draft v1.0
> **Note:** This document covers the Family Office Portal -- a new project that will
> consume `llc-manager`, `xero_crypto`, `pp-security-master`, and `family_office` as
> backend services. It lives here temporarily pending creation of a dedicated portal repo.

---

## 1. The Problem

Two family members (the primary users) need regular visibility into a complex,
multi-entity estate. That estate spans legal entities (LLCs, trusts), investment
portfolios (equities, alternatives, crypto), compliance obligations, and decades of
estate planning documents.

Today, accessing this information requires:

- Navigating multiple professional systems owned by lawyers, accountants, and custodians
- Logging in and out of separate tools (Kubera, Portfolio Performance, Box)
- Calling a family member or advisor to answer a basic question like "are our LLCs in
  compliance?" or "what is our net worth today?"

The result: two users who are capable of making sound decisions about their estate are
effectively locked out of the information they need to do so independently.

---

## 2. The Vision

A single, secure web portal that presents a consolidated view of the estate.

One URL. One login. Everything they need.

Documents, financial summaries, entity compliance status, and portfolio performance
presented clearly, without jargon, without navigation complexity, and without
requiring any technical knowledge to use.

---

## 3. Users

### 3.1 Primary Users -- Parents (2 people)

These are the people the portal is built for. Everything else is in service of them.

| Attribute | Detail |
|---|---|
| Technical proficiency | Very low -- comfortable with tablets, email, and basic web browsing |
| Primary device | Tablet (iPad-class) and desktop browser |
| Usage pattern | Occasional -- a few times per week, usually to check something specific |
| Tolerance for complexity | Near zero -- any friction creates a support call |

**What they want to know:**

- "Where is [specific document]?"
- "How is our money doing?"
- "Which LLCs do we have, and are any of them overdue for something?"
- "What does [tax/legal term] mean for us?"

**What they must never have to do:**

- Remember a password
- Navigate more than two levels deep to find anything
- See a blank screen, error message, or loading spinner that doesn't resolve
- Leave the portal to find information

### 3.2 Administrator (1-2 people)

Family member(s) who manage documents, monitor data freshness, and handle
configuration. Moderately technical. Not the focus of the design effort -- admin
views can be utilitarian.

---

## 4. Design Principles

These are not preferences -- they are constraints the design must satisfy.

### 4.1 One Door In

All content is accessible through a single URL. No external links, no "click here to
open in [provider]," no redirects to other services. If the user has to leave the
portal to find something, the portal has failed.

### 4.2 Clarity Over Completeness

The portal does not show everything -- it shows what matters. Raw data (account
numbers, ticker symbols, legal entity identifiers) is labeled plainly or hidden
entirely. Summaries precede detail. Charts before tables.

### 4.3 Read-Only by Default

Primary users cannot accidentally change, delete, or submit anything. Every
interaction is a view or a download.

### 4.4 Resilient to Data Freshness

If a backend service is slow or temporarily unavailable, the portal shows cached data
with a clear timestamp ("last updated 3 hours ago"). It never shows a blank section
or an unhandled error. Stale data with a label is better than nothing.

### 4.5 Progressive Disclosure

Each section leads with a summary. Detail is available on demand -- one tap or click
deeper, never buried. The home screen answers the most common questions without
requiring any navigation at all.

### 4.6 Zero Jargon

Every label, heading, and piece of body text is written in plain English. Assume no
prior knowledge of investment, tax, or legal terminology. When technical terms are
unavoidable, they are explained inline.

---

## 5. Information Architecture

### 5.1 Top-Level Sections

Five sections, accessible from a persistent top navigation bar. No sub-menus.

| # | Section | Purpose |
|---|---|---|
| 1 | Home | Dashboard summary -- quick answers to the most common questions |
| 2 | Documents | Estate documents organized by category, searchable, downloadable |
| 3 | Finances | Net worth, account balances, asset allocation (Kubera data) |
| 4 | Portfolio | Investment performance, holdings, sector allocation |
| 5 | Entities | LLC and trust compliance status, key dates, ownership |

A sixth section, **Ask**, is planned for a future phase (see Section 9).

### 5.2 Navigation Rules

- Maximum five top-level items in the navigation bar
- Maximum two levels of depth anywhere in the information architecture
- Active section is always clearly indicated
- Back navigation is always available and obvious
- The user's current location is always visible

---

## 6. Screen-by-Screen Requirements

### 6.1 Home -- Dashboard

**Purpose:** Answer the three most common questions without requiring any navigation.

**Content:**

- **Net worth summary** -- a single prominent number with a trend indicator
  (up/down from last month, percentage change)
- **Upcoming dates** -- the next three compliance, filing, or renewal deadlines
  across all entities, in plain English ("Annual Report due for [LLC Name] in 14 days")
- **Portfolio snapshot** -- simplified performance for the current month and year-to-date
- **Recent documents** -- the three most recently added or updated documents, with
  a one-click download

**States to design:**

- All data current (nominal state)
- One or more sections showing cached data (partial degraded state)
- First load / no data yet (empty state)

### 6.2 Documents

**Purpose:** Find and access any estate document without needing to know where it is
stored or who manages it.

**Content:**

- Folder view organized by category: Estate Planning, LLCs, Trusts, Tax Returns,
  Insurance, Other
- Search bar (name search minimum; full-text search future state)
- Each document shows: name, category, date added/modified, download button
- PDF preview on tap/click (inline, not a new tab)

**States to design:**

- Populated folder view
- Empty category
- Search with results
- Search with no results

### 6.3 Finances

**Purpose:** Understand the overall financial picture -- total wealth, where it sits,
and how it is allocated.

**Content:**

- Net worth over time (line chart, selectable range: 3M, 6M, 1Y, all)
- Breakdown by asset class (pie or bar chart): equities, real estate, alternatives,
  crypto, cash
- Account list: institution name, account type, current balance
- All figures in USD; non-USD assets converted and labeled as approximate

**States to design:**

- Full data state
- Partial data (some accounts unavailable)
- Data older than 24 hours (prominent staleness indicator)

### 6.4 Portfolio

**Purpose:** Understand investment performance and what is held.

**Content:**

- Performance chart (line, selectable range), showing total return vs a relevant
  benchmark (S&P 500 minimum)
- Holdings table: security name (not ticker), sector, current value, allocation
  percentage, gain/loss
- Sector allocation chart
- Transactions view (recent, paginated -- not the default view)

**Design note:** Security names should be plain English ("Apple Inc." not "AAPL").
Allocation percentages matter more than absolute dollar precision.

**States to design:**

- Populated with current data
- No transactions yet (new account / empty state)
- Data refresh in progress

### 6.5 Entities

**Purpose:** Know which LLCs and trusts exist, whether they are in good standing,
and when action is required.

**Content:**

- Entity list with a status indicator per entity: green (current), yellow (due
  within 60 days), red (overdue or missing data)
- Each entity shows: name, type (LLC / Trust), state, registered agent, next
  key date
- Detail view per entity: all key dates, ownership structure (plain English
  summary), associated documents (linked to Documents section)

**States to design:**

- All entities current
- One or more entities requiring attention (alert state)
- Entity with incomplete data

---

## 7. Authentication and Session Behavior

### 7.1 Login

- Cloudflare Zero Trust handles authentication
- Users receive a one-time email link (no password to remember or manage)
- "Remember this device" enabled by default -- users should not be asked to
  re-authenticate frequently on their own devices

### 7.2 Session

- Sessions persist for an extended period on trusted devices (target: 30 days)
- Session expiry shows a clear, plain-language prompt ("You've been logged out for
  security. Tap here to log back in.")
- No automatic logout during active use

### 7.3 Access Levels

| Level | Who | Capabilities |
|---|---|---|
| Viewer | Parents | Read, search, download documents |
| Admin | Family manager | All viewer capabilities plus data refresh, user management |

---

## 8. Technical Context for Designers

The portal is a presentation layer over four existing backend services. Designers
do not need to understand these systems in depth, but knowing they exist avoids
designing for data that cannot be delivered.

| Backend | What it provides | Availability |
|---|---|---|
| `llc-manager` | LLC and trust entities, compliance dates, ownership | Mature (v0.1.0) |
| `pp-security-master` | Investment holdings, classifications, performance | Alpha |
| `xero_crypto` | Crypto portfolio positions and reconciliation | v1.0.0 |
| `family_office` | Tax and estate law knowledge base for Q&A | Active |

**Key constraint:** The portal never connects directly to Kubera, Google Drive, or
Portfolio Performance's UI. All data is pulled by backend services, cached locally,
and served through a single API. Designers can treat the data layer as a black box.

**Frontend technology:** The portal will be built with server-rendered HTML (HTMX +
Jinja2 + Tailwind CSS). This means:

- No single-page application patterns
- Standard link and form behavior
- Fast, reliable page loads
- Consistent browser history and back-button behavior

This is a feature, not a constraint -- it produces a more reliable experience for
low-proficiency users than a JavaScript-heavy SPA.

---

## 9. Future State -- Ask

A natural language Q&A interface backed by the `family_office` tax law knowledge
base. Users can ask plain-English questions ("Can our LLC pay for the roof repair?",
"What is the gift tax exclusion this year?") and receive sourced, plain-English
answers.

This section is excluded from the initial design scope. When included, it will appear
as a sixth top-level section with a simple chat-style interface. Key design
requirements for future reference:

- Clearly labeled as educational information, not legal or financial advice
- Sources displayed with every answer (statute, regulation, or case name)
- Plain English answers with no legal jargon unless defined inline
- No conversation history stored between sessions (privacy)

---

## 10. Success Criteria

The portal is successful when:

1. Both parents can locate any specific document in under two minutes without
   assistance.
2. Both parents can answer "what is our net worth today?" independently, without
   calling anyone.
3. LLC compliance status is visible at a glance from the home screen.
4. The system operates for at least two weeks without requiring manual intervention
   or generating a support request.
5. Both parents describe the portal as easy to use without prompting.

---

## 11. Out of Scope

The design team is not responsible for the following. These are implementation
concerns handled by the backend team.

- Database schema or API design
- Authentication system implementation
- Data ingestion pipelines (Kubera sync, market data refresh, XML parsing)
- Document storage infrastructure
- Crypto reconciliation internals
- LLM infrastructure for the Ask feature

---

## 12. Open Questions for Design Team

The following questions require design input before implementation begins.

1. **Home screen hierarchy:** What is the primary visual emphasis on the home screen --
   net worth, compliance status, or recent documents? These compete for attention and
   the priority should reflect what the users reach for most.

2. **Data freshness communication:** How prominently should staleness indicators appear?
   A banner, a small timestamp, a color change on affected sections? The right answer
   balances transparency with visual noise.

3. **Compliance status language:** Red/yellow/green is conventional but may carry
   anxiety for users who see a red indicator. Consider whether neutral language
   ("Review needed" vs "Overdue") is preferable, or whether urgency communication
   is a feature.

4. **Mobile breakpoints:** Tablet is the primary device. Is a phone-optimized layout
   in scope for the initial release, or is tablet-and-desktop the first target?

5. **Empty states:** Several sections will be empty or sparse during initial data
   population. What should users see before the backend has synced? A skeleton,
   a friendly message, a progress indicator?

6. **Ask feature placement (future):** When the Q&A feature ships, should it live in
   the top navigation as a sixth section, or as a persistent floating button
   accessible from every screen?

---

## 13. Appendix -- Glossary

Terms the design team may encounter in conversations with the backend team.

| Term | Plain English |
|---|---|
| LLC | A type of legal business entity used to hold assets |
| Trust | A legal arrangement for holding and transferring assets |
| GICS | A system for categorizing stocks by industry sector |
| OHLC | Open, high, low, close -- four daily price points for a stock |
| ETL | Extract, transform, load -- the process of moving and cleaning data |
| Kubera | Third-party financial aggregation service tracking net worth |
| Portfolio Performance | Open-source investment tracking desktop application |
| HTMX | A web technology that makes pages update without full reloads |
