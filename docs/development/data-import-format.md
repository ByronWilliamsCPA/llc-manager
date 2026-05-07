---
title: "Data Import Format Specification"
schema_type: common
status: published
owner: core-maintainer
purpose: "Canonical Excel workbook layout expected by scripts/import_excel.py."
tags:
  - development
  - guide
---

This document defines the structure of the Excel workbook that `scripts/import_excel.py`
accepts for bulk-importing LLC entity data. Each tab name is exact and case-sensitive.
The import script resolves relationships between tabs using the `entity_legal_name` column,
which must match the `legal_name` value in the `Entities` tab exactly (including
capitalization and punctuation).

## General Rules

- All dates must be in `YYYY-MM-DD` format (e.g., `2024-03-15`).
- Boolean columns accept `TRUE`, `FALSE`, `1`, or `0` (case-insensitive).
- Numeric columns use standard decimal notation (e.g., `50.00` for 50%).
- Empty cells are treated as `NULL` for optional fields.
- The `Entities` tab must be populated before any related tabs, as FK lookups
  depend on entity records existing.
- Rows with all columns empty are silently skipped.

---

## **Entities**

Maps to the `Entity` model. This is the root tab; all other tabs reference rows
here by `legal_name`.

| Column Name | Required | Validation Rule | Example |
|---|---|---|---|
| `legal_name` | Required | Non-empty string, max 255 chars. Must be unique across the workbook. | `Acme Holdings LLC` |
| `entity_type` | Optional | One of: `llc`, `corporation`, `s_corporation`, `partnership`, `sole_proprietorship`, `trust`, `non_profit`, `other`. Defaults to `llc` if omitted. | `llc` |
| `dba_names` | Optional | Free text; separate multiple DBAs with commas | `Acme Realty, Acme Dev` |
| `ein` | Required | String matching `XX-XXXXXXX` pattern (9 digits), globally unique | `12-3456789` |
| `formation_state` | Optional | Two-letter US state abbreviation (uppercase) | `TX` |
| `formation_date` | Optional | `YYYY-MM-DD` | `2019-06-01` |
| `fiscal_year_end` | Optional | `MM-DD` format, max 5 chars | `12-31` |
| `business_address` | Optional | Street address, max 255 chars | `100 Main St` |
| `business_city` | Optional | City name, max 100 chars | `Austin` |
| `business_state` | Optional | Two-letter US state abbreviation (uppercase) | `TX` |
| `business_zip` | Optional | ZIP or ZIP+4, max 10 chars | `78701` |
| `mailing_address` | Optional | Street address, max 255 chars; omit if same as business address | `PO Box 500` |
| `mailing_city` | Optional | City name, max 100 chars | `Austin` |
| `mailing_state` | Optional | Two-letter US state abbreviation (uppercase) | `TX` |
| `mailing_zip` | Optional | ZIP or ZIP+4, max 10 chars | `78701-0500` |
| `accounting_record_id` | Optional | External system record ID, max 100 chars | `QBO-1042` |
| `purpose` | Optional | Free text description of business purpose | `Real estate investment and management` |
| `notes` | Optional | Free text; additional context about the entity | `Formed to hold rental properties` |
| `is_active` | Optional | Boolean. Defaults to `TRUE` if omitted. | `TRUE` |

---

## **Owners**

Maps to the `Owner` model. Each row is linked to an entity via `entity_legal_name`.

**FK lookup**: The value in `entity_legal_name` must exactly match a `legal_name`
value in the `Entities` tab. Rows with an unresolved `entity_legal_name` are
rejected with a validation error.

| Column Name | Required | Validation Rule | Example |
|---|---|---|---|
| `entity_legal_name` | Required | Must match a `legal_name` in the `Entities` tab | `Acme Holdings LLC` |
| `owner_name` | Required | Non-empty string, max 255 chars | `Jane Smith` |
| `ownership_type` | Optional | One of: `member`, `managing_member`, `shareholder`, `general_partner`, `limited_partner`, `beneficiary`, `trustee`, `director`, `officer`. Defaults to `member` if omitted. | `managing_member` |
| `ownership_percentage` | Required | Decimal 0.00-100.00 (5 digits, 2 decimal places). All owners for an entity should sum to 100. | `60.00` |
| `owner_entity_legal_name` | Optional | Legal name of the owning entity if the owner is itself an entity in this workbook | `Smith Family Trust LLC` |
| `capital_contribution` | Optional | Decimal amount up to 15 digits with 2 decimal places | `50000.00` |
| `profit_share_percentage` | Optional | Decimal 0.00-100.00; omit if same as `ownership_percentage` | `60.00` |
| `loss_share_percentage` | Optional | Decimal 0.00-100.00; omit if same as `ownership_percentage` | `60.00` |
| `voting_percentage` | Optional | Decimal 0.00-100.00; omit if same as `ownership_percentage` | `60.00` |
| `start_date` | Optional | `YYYY-MM-DD` | `2019-06-01` |
| `end_date` | Optional | `YYYY-MM-DD`; leave blank for current owners | `2023-12-31` |
| `ein_or_ssn` | Optional | EIN (`XX-XXXXXXX`) or SSN (`XXX-XX-XXXX`). Stored encrypted; handle with care. | `98-7654321` |
| `address` | Optional | Street address, max 255 chars | `200 Oak Ave` |
| `city` | Optional | City name, max 100 chars | `Dallas` |
| `state` | Optional | Two-letter US state abbreviation (uppercase) | `TX` |
| `zip_code` | Optional | ZIP or ZIP+4, max 10 chars | `75201` |
| `email` | Optional | Valid email address, max 255 chars | `jane@example.com` |
| `phone` | Optional | Phone number, max 20 chars | `512-555-0100` |
| `notes` | Optional | Free text | `Original founding member` |
| `is_active` | Optional | Boolean. Defaults to `TRUE` if omitted. | `TRUE` |

---

## **StateRegistrations**

Maps to the `StateRegistration` model. Each row links to an entity via `entity_legal_name`.

**FK lookup**: The value in `entity_legal_name` must exactly match a `legal_name`
in the `Entities` tab. The combination of `entity_legal_name`, `state`, and
`registration_type` must be unique within the workbook (mirrors the database
unique constraint `uq_entity_state_type`).

| Column Name | Required | Validation Rule | Example |
|---|---|---|---|
| `entity_legal_name` | Required | Must match a `legal_name` in the `Entities` tab | `Acme Holdings LLC` |
| `state` | Required | Two-letter US state abbreviation (uppercase) | `CA` |
| `registration_type` | Optional | One of: `domestic`, `foreign`, `assumed_name`, `professional`, `specialty`. Defaults to `domestic` if omitted. | `foreign` |
| `status` | Optional | One of: `active`, `pending`, `expired`, `withdrawn`, `revoked`, `suspended`, `reinstated`. Defaults to `active` if omitted. | `active` |
| `file_number` | Optional | State-assigned file or registration number, max 50 chars | `202312345678` |
| `registered_name` | Optional | Name as registered in this state if different from legal name, max 255 chars | `Acme Holdings Foreign LLC` |
| `registration_date` | Optional | `YYYY-MM-DD` | `2021-03-10` |
| `effective_date` | Optional | `YYYY-MM-DD` | `2021-03-15` |
| `expiration_date` | Optional | `YYYY-MM-DD` | `2025-03-14` |
| `annual_report_due` | Optional | `YYYY-MM-DD` | `2024-06-01` |
| `last_annual_report` | Optional | `YYYY-MM-DD` | `2023-05-30` |
| `next_renewal_date` | Optional | `YYYY-MM-DD` | `2025-03-01` |
| `filing_fee` | Optional | Fee amount as a string, max 50 chars | `150.00` |
| `annual_fee` | Optional | Annual maintenance fee as a string, max 50 chars | `25.00` |
| `is_good_standing` | Optional | Boolean. Defaults to `TRUE` if omitted. | `TRUE` |
| `notes` | Optional | Free text | `Foreign qualification required for CA operations` |

---

## **BankAccounts**

Maps to the `BankAccount` model. Each row links to an entity via `entity_legal_name`.

**FK lookup**: The value in `entity_legal_name` must exactly match a `legal_name`
in the `Entities` tab.

| Column Name | Required | Validation Rule | Example |
|---|---|---|---|
| `entity_legal_name` | Required | Must match a `legal_name` in the `Entities` tab | `Acme Holdings LLC` |
| `bank_name` | Required | Name of the bank or financial institution, max 255 chars | `First National Bank` |
| `account_type` | Optional | One of: `checking`, `savings`, `money_market`, `cd`, `business_checking`, `business_savings`, `merchant_account`, `payroll`, `other`. Defaults to `business_checking` if omitted. | `business_checking` |
| `account_name` | Optional | Name on the account, max 255 chars | `Acme Holdings LLC Operating` |
| `account_number_last4` | Optional | Last 4 digits of account number only, exactly 4 digits | `4321` |
| `routing_number` | Optional | 9-digit ABA routing number | `021000021` |
| `account_nickname` | Optional | Short label for easy identification, max 100 chars | `Operating Account` |
| `opened_date` | Optional | `YYYY-MM-DD` | `2019-07-15` |
| `closed_date` | Optional | `YYYY-MM-DD`; leave blank for open accounts | `2023-11-30` |
| `primary_contact` | Optional | Name of the primary bank contact, max 255 chars | `Tom Banker` |
| `contact_phone` | Optional | Phone number, max 20 chars | `512-555-0200` |
| `contact_email` | Optional | Valid email address, max 255 chars | `tom.banker@fnb.com` |
| `branch_address` | Optional | Full branch address as free text | `500 Congress Ave, Austin, TX 78701` |
| `online_banking_url` | Optional | URL for online banking portal, max 500 chars | `https://online.fnb.com` |
| `is_primary` | Optional | Boolean. Defaults to `FALSE` if omitted. Only one account per entity should be marked `TRUE`. | `TRUE` |
| `is_active` | Optional | Boolean. Defaults to `TRUE` if omitted. | `TRUE` |
| `notes` | Optional | Free text | `Primary operating account since formation` |

---

## **TaxFilings**

Maps to the `TaxFiling` model. Each row links to an entity via `entity_legal_name`.

**FK lookup**: The value in `entity_legal_name` must exactly match a `legal_name`
in the `Entities` tab.

| Column Name | Required | Validation Rule | Example |
|---|---|---|---|
| `entity_legal_name` | Required | Must match a `legal_name` in the `Entities` tab | `Acme Holdings LLC` |
| `filing_type` | Required | One of: `federal_income`, `state_income`, `franchise_tax`, `sales_tax`, `payroll_tax`, `property_tax`, `estimated_tax`, `annual_report`, `k1`, `other` | `federal_income` |
| `jurisdiction` | Required | Two-letter state abbreviation or `Federal`, max 50 chars | `Federal` |
| `tax_year` | Required | Four-digit integer year | `2023` |
| `frequency` | Optional | One of: `annual`, `quarterly`, `monthly`, `semi_annual`, `one_time`. Defaults to `annual` if omitted. | `annual` |
| `status` | Optional | One of: `pending`, `filed`, `extended`, `late`, `not_required`. Defaults to `pending` if omitted. | `filed` |
| `tax_period` | Optional | Specific period within the year, max 20 chars | `Q1 2023` |
| `due_date` | Optional | `YYYY-MM-DD` | `2024-04-15` |
| `extended_due_date` | Optional | `YYYY-MM-DD`; populate only when an extension has been filed | `2024-10-15` |
| `filed_date` | Optional | `YYYY-MM-DD`; populate only when `status` is `filed` | `2024-03-28` |
| `form_number` | Optional | Tax form identifier, max 50 chars | `1065` |
| `confirmation_number` | Optional | Filing confirmation number, max 100 chars | `0123456789ABCDEF` |
| `preparer` | Optional | Name of tax preparer, max 255 chars | `Williams CPA` |
| `amount_due` | Optional | Amount due as a string (no currency symbol), max 50 chars | `1500.00` |
| `amount_paid` | Optional | Amount paid as a string (no currency symbol), max 50 chars | `1500.00` |
| `notes` | Optional | Free text | `Extension filed 2024-04-12; payment submitted with extension` |

---

## **RegisteredAgents**

Maps to the `RegisteredAgent` model. Each row links to an entity via `entity_legal_name`.

**FK lookup**: The value in `entity_legal_name` must exactly match a `legal_name`
in the `Entities` tab. Unique constraint: `(entity_id, state, is_active)` -- one active agent
per state per entity, and also one inactive agent per state per entity.

| Column Name | Required | Validation Rule | Example |
|---|---|---|---|
| `entity_legal_name` | Required | Must match a `legal_name` in the `Entities` tab | `Acme Holdings LLC` |
| `state` | Required | Two-letter US state abbreviation (uppercase) where the agent is registered | `TX` |
| `agent_name` | Required | Full name of the registered agent (person), max 255 chars | `Registered Agents Inc` |
| `agent_company` | Optional | Company name of the registered agent service, max 255 chars | `Registered Agents Inc` |
| `address` | Optional | Street address of the registered agent, max 255 chars | `1234 Agent Blvd` |
| `city` | Optional | City of the registered agent, max 100 chars | `Austin` |
| `state_address` | Optional | State of the registered agent address (may differ from `state`), two-letter abbreviation | `TX` |
| `zip_code` | Optional | ZIP or ZIP+4 of the registered agent, max 10 chars | `78701` |
| `phone` | Optional | Phone number, max 20 chars | `800-555-0300` |
| `email` | Optional | Valid email address, max 255 chars | `service@ragents.com` |
| `effective_date` | Optional | `YYYY-MM-DD` | `2019-06-01` |
| `expiration_date` | Optional | `YYYY-MM-DD` | `2025-05-31` |
| `renewal_date` | Optional | `YYYY-MM-DD`; date the service must be renewed | `2025-04-01` |
| `annual_cost` | Optional | Annual cost as a string, max 50 chars | `149.00` |
| `account_number` | Optional | Account number with the registered agent service, max 100 chars | `RA-00123456` |
| `is_active` | Optional | Boolean. Defaults to `TRUE` if omitted. | `TRUE` |
| `notes` | Optional | Free text | `Switched from prior agent 2021-01-01` |
