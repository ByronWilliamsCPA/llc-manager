#!/usr/bin/env python3
"""Seed data generator for LLC Manager development.

Creates realistic test entities with related records (owners, state registrations,
bank accounts, etc.) for development and testing purposes.

Usage:
    uv run python scripts/seed.py --entities 10
    uv run python scripts/seed.py --entities 5 --clear
"""

import argparse
import asyncio
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc_manager.core.config import settings
from llc_manager.models import (
    BankAccount,
    Document,
    DocumentType,
    Entity,
    EntityType,
    Owner,
    OwnershipType,
    RegisteredAgent,
    StateRegistration,
    TaxFiling,
    TaxFilingType,
)
from llc_manager.models.bank_account import AccountType
from llc_manager.models.state_registration import RegistrationStatus, RegistrationType
from llc_manager.models.tax_filing import FilingFrequency, FilingStatus

# Realistic test data
COMPANY_PREFIXES = [
    "Mountain View",
    "Coastal",
    "Sunset",
    "Heritage",
    "Summit",
    "Valley",
    "Golden Gate",
    "Pacific",
    "Riverside",
    "Lakeside",
    "Evergreen",
    "Redwood",
    "Sterling",
    "Pinnacle",
    "Horizon",
]

COMPANY_SUFFIXES = [
    "Properties",
    "Holdings",
    "Investments",
    "Capital",
    "Partners",
    "Ventures",
    "Management",
    "Development",
    "Real Estate",
    "Enterprises",
]

FIRST_NAMES = [
    "James",
    "Sarah",
    "Michael",
    "Emily",
    "Robert",
    "Jennifer",
    "William",
    "Elizabeth",
    "David",
    "Margaret",
]

LAST_NAMES = [
    "Williams",
    "Johnson",
    "Smith",
    "Anderson",
    "Thompson",
    "Garcia",
    "Martinez",
    "Brown",
    "Davis",
    "Wilson",
]

STATES = ["CA", "TX", "NY", "FL", "NV", "DE", "WY", "CO", "AZ", "WA"]

BANKS = [
    "First National Bank",
    "Chase",
    "Bank of America",
    "Wells Fargo",
    "US Bank",
    "Citibank",
    "Capital One",
    "PNC Bank",
]

REGISTERED_AGENT_COMPANIES = [
    "CT Corporation",
    "CSC Global",
    "Registered Agent Solutions",
    "Northwest Registered Agent",
    "LegalZoom",
    "Incfile",
]

STREET_NAMES = [
    "Main Street",
    "Oak Avenue",
    "Commerce Drive",
    "Industrial Blvd",
    "Park Place",
    "First Street",
    "Market Street",
    "Business Center Drive",
]

CITIES = {
    "CA": ["Los Angeles", "San Francisco", "San Diego", "Sacramento"],
    "TX": ["Houston", "Dallas", "Austin", "San Antonio"],
    "NY": ["New York", "Buffalo", "Albany", "Rochester"],
    "FL": ["Miami", "Orlando", "Tampa", "Jacksonville"],
    "NV": ["Las Vegas", "Reno", "Henderson", "Carson City"],
    "DE": ["Wilmington", "Dover", "Newark", "Middletown"],
    "WY": ["Cheyenne", "Casper", "Laramie", "Gillette"],
    "CO": ["Denver", "Colorado Springs", "Boulder", "Fort Collins"],
    "AZ": ["Phoenix", "Tucson", "Scottsdale", "Mesa"],
    "WA": ["Seattle", "Spokane", "Tacoma", "Bellevue"],
}


def generate_ein() -> str:
    """Generate a random but valid-format EIN."""
    prefix = random.randint(10, 99)
    suffix = random.randint(1000000, 9999999)
    return f"{prefix}-{suffix}"


def generate_phone() -> str:
    """Generate a random phone number."""
    area = random.randint(200, 999)
    prefix = random.randint(200, 999)
    suffix = random.randint(1000, 9999)
    return f"({area}) {prefix}-{suffix}"


def generate_email(name: str) -> str:
    """Generate an email based on name."""
    clean_name = name.lower().replace(" ", ".").replace(",", "")
    domains = ["gmail.com", "outlook.com", "company.com", "business.net"]
    return f"{clean_name}@{random.choice(domains)}"


def random_date_in_range(start_year: int, end_year: int) -> date:
    """Generate a random date within a year range."""
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    return start + timedelta(days=random_days)


def generate_company_name() -> str:
    """Generate a random company name."""
    prefix = random.choice(COMPANY_PREFIXES)
    suffix = random.choice(COMPANY_SUFFIXES)
    return f"{prefix} {suffix}"


def create_entity(idx: int) -> Entity:
    """Create a test entity with realistic data."""
    formation_state = random.choice(STATES)
    formation_date = random_date_in_range(2010, 2024)

    city = random.choice(CITIES[formation_state])
    street_num = random.randint(100, 9999)
    street = random.choice(STREET_NAMES)

    return Entity(
        id=uuid4(),
        legal_name=f"{generate_company_name()}, LLC",
        dba_names=f"Test DBA {idx}" if random.random() > 0.7 else None,
        ein=generate_ein(),
        entity_type=random.choice(
            [EntityType.LLC, EntityType.LLC, EntityType.S_CORPORATION]
        ),
        formation_state=formation_state,
        formation_date=formation_date,
        fiscal_year_end="12-31",
        business_address=f"{street_num} {street}",
        business_city=city,
        business_state=formation_state,
        business_zip=f"{random.randint(10000, 99999)}",
        accounting_record_id=f"ACC-{idx:04d}",
        purpose="Real estate investment and property management",
        is_active=True,
    )


def create_owners(entity: Entity, count: int = 2) -> list[Owner]:
    """Create test owners for an entity."""
    owners = []
    remaining_pct = Decimal("100.00")

    for i in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"

        if i == count - 1:
            pct = remaining_pct
        else:
            pct = Decimal(str(random.randint(20, 60)))
            remaining_pct -= pct

        state = random.choice(STATES)
        city = random.choice(CITIES[state])

        owner = Owner(
            id=uuid4(),
            entity_id=entity.id,
            owner_name=name,
            ownership_type=(
                OwnershipType.MANAGING_MEMBER if i == 0 else OwnershipType.MEMBER
            ),
            ownership_percentage=pct,
            capital_contribution=Decimal(str(random.randint(10000, 500000))),
            start_date=entity.formation_date,
            address=f"{random.randint(100, 9999)} {random.choice(STREET_NAMES)}",
            city=city,
            state=state,
            zip_code=f"{random.randint(10000, 99999)}",
            email=generate_email(name),
            phone=generate_phone(),
            is_active=True,
        )
        owners.append(owner)

    return owners


def create_state_registration(entity: Entity) -> StateRegistration:
    """Create a domestic state registration for the entity."""
    formation_date = entity.formation_date or datetime.now(tz=UTC).date()
    annual_report_month = random.randint(1, 12)

    return StateRegistration(
        id=uuid4(),
        entity_id=entity.id,
        state=entity.formation_state or "CA",
        registration_type=RegistrationType.DOMESTIC,
        status=RegistrationStatus.ACTIVE,
        file_number=f"{entity.formation_state}{random.randint(100000, 999999)}",
        registration_date=formation_date,
        effective_date=formation_date,
        annual_report_due=date(
            datetime.now(tz=UTC).date().year, annual_report_month, 1
        ),
        last_annual_report=date(
            datetime.now(tz=UTC).date().year - 1, annual_report_month, 15
        ),
        filing_fee="$70.00",
        annual_fee="$25.00",
        is_good_standing=True,
    )


def create_registered_agent(entity: Entity, state: str) -> RegisteredAgent:
    """Create a registered agent for an entity in a state."""
    agent_company = random.choice(REGISTERED_AGENT_COMPANIES)
    city = random.choice(CITIES.get(state, ["City"]))

    return RegisteredAgent(
        id=uuid4(),
        entity_id=entity.id,
        state=state,
        agent_name="Registered Agent Service",
        agent_company=agent_company,
        address=f"{random.randint(100, 999)} Business Park Drive, Suite {random.randint(100, 500)}",
        city=city,
        state_address=state,
        zip_code=f"{random.randint(10000, 99999)}",
        phone=generate_phone(),
        email=f"service@{agent_company.lower().replace(' ', '')}.com",
        effective_date=entity.formation_date,
        renewal_date=date(datetime.now(tz=UTC).date().year + 1, 1, 1),
        annual_cost="$99.00",
        is_active=True,
    )


def create_bank_account(entity: Entity) -> BankAccount:
    """Create a bank account for an entity."""
    bank = random.choice(BANKS)

    return BankAccount(
        id=uuid4(),
        entity_id=entity.id,
        bank_name=bank,
        account_name=entity.legal_name,
        account_type=AccountType.BUSINESS_CHECKING,
        account_number_last4=f"{random.randint(1000, 9999)}",
        routing_number=f"{random.randint(100000000, 999999999)}"[:9],
        account_nickname="Operating Account",
        opened_date=entity.formation_date,
        primary_contact="Business Banking Team",
        contact_phone=generate_phone(),
        contact_email=f"business@{bank.lower().replace(' ', '')}.com",
        online_banking_url=f"https://www.{bank.lower().replace(' ', '')}.com/business",
        is_primary=True,
        is_active=True,
    )


def create_tax_filings(entity: Entity) -> list[TaxFiling]:
    """Create tax filing records for an entity."""
    current_year = datetime.now(tz=UTC).date().year
    filings = []

    # Federal income tax
    filings.append(
        TaxFiling(
            id=uuid4(),
            entity_id=entity.id,
            filing_type=TaxFilingType.FEDERAL_INCOME,
            jurisdiction="Federal",
            tax_year=current_year - 1,
            frequency=FilingFrequency.ANNUAL,
            due_date=date(current_year, 3, 15),
            extended_due_date=date(current_year, 9, 15),
            status=FilingStatus.FILED,
            filed_date=date(current_year, 3, 10),
            form_number="1065",
            preparer="Smith & Associates CPA",
        )
    )

    # State tax if applicable
    if entity.formation_state in ["CA", "NY", "TX"]:
        filings.append(
            TaxFiling(
                id=uuid4(),
                entity_id=entity.id,
                filing_type=TaxFilingType.STATE_INCOME,
                jurisdiction=entity.formation_state or "CA",
                tax_year=current_year - 1,
                frequency=FilingFrequency.ANNUAL,
                due_date=date(current_year, 4, 15),
                status=FilingStatus.FILED,
                filed_date=date(current_year, 4, 1),
                form_number="568" if entity.formation_state == "CA" else "IT-204",
                preparer="Smith & Associates CPA",
            )
        )

    # Current year pending
    filings.append(
        TaxFiling(
            id=uuid4(),
            entity_id=entity.id,
            filing_type=TaxFilingType.FEDERAL_INCOME,
            jurisdiction="Federal",
            tax_year=current_year,
            frequency=FilingFrequency.ANNUAL,
            due_date=date(current_year + 1, 3, 15),
            status=FilingStatus.PENDING,
            form_number="1065",
        )
    )

    return filings


def create_documents(entity: Entity) -> list[Document]:
    """Create document records for an entity."""
    documents = []

    # Articles of Organization
    documents.append(
        Document(
            id=uuid4(),
            entity_id=entity.id,
            document_type=DocumentType.ARTICLES_OF_ORGANIZATION,
            title=f"Articles of Organization - {entity.legal_name}",
            description="Original filed articles of organization",
            document_date=entity.formation_date,
            effective_date=entity.formation_date,
            file_path=f"/documents/{entity.id}/articles_of_organization.pdf",
            is_confidential=False,
        )
    )

    # Operating Agreement
    documents.append(
        Document(
            id=uuid4(),
            entity_id=entity.id,
            document_type=DocumentType.OPERATING_AGREEMENT,
            title=f"Operating Agreement - {entity.legal_name}",
            description="Current operating agreement",
            document_date=entity.formation_date,
            effective_date=entity.formation_date,
            file_path=f"/documents/{entity.id}/operating_agreement.pdf",
            is_confidential=True,
        )
    )

    # EIN Letter
    documents.append(
        Document(
            id=uuid4(),
            entity_id=entity.id,
            document_type=DocumentType.EIN_LETTER,
            title=f"IRS EIN Confirmation - {entity.legal_name}",
            description="IRS EIN assignment letter",
            document_date=entity.formation_date,
            file_path=f"/documents/{entity.id}/ein_letter.pdf",
            is_confidential=True,
        )
    )

    return documents


async def clear_all_data(session: AsyncSession) -> None:
    """Clear all existing data from the database."""
    print("Clearing existing data...")

    # Delete in reverse order of dependencies
    await session.execute(text("DELETE FROM tax_filings"))
    await session.execute(text("DELETE FROM documents"))
    await session.execute(text("DELETE FROM registered_agents"))
    await session.execute(text("DELETE FROM bank_accounts"))
    await session.execute(text("DELETE FROM state_registrations"))
    await session.execute(text("DELETE FROM owners"))
    await session.execute(text("DELETE FROM entity_relationships"))
    await session.execute(text("DELETE FROM entities"))

    await session.commit()
    print("All data cleared.")


async def seed_database(num_entities: int, clear: bool = False) -> None:
    """Generate and insert seed data."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        if clear:
            await clear_all_data(session)

        # Check for existing entities
        result = await session.execute(select(Entity).limit(1))
        if result.scalar_one_or_none():
            print("Database already contains entities. Use --clear to reset.")
            return

        print(f"Generating {num_entities} test entities...")

        for i in range(num_entities):
            # Create entity
            entity = create_entity(i + 1)
            session.add(entity)

            # Create related records
            owners = create_owners(entity, count=random.randint(1, 3))
            for owner in owners:
                session.add(owner)

            state_reg = create_state_registration(entity)
            session.add(state_reg)

            registered_agent = create_registered_agent(
                entity, entity.formation_state or "CA"
            )
            session.add(registered_agent)

            bank_account = create_bank_account(entity)
            session.add(bank_account)

            tax_filings = create_tax_filings(entity)
            for filing in tax_filings:
                session.add(filing)

            documents = create_documents(entity)
            for doc in documents:
                session.add(doc)

            print(f"  Created: {entity.legal_name}")

        await session.commit()
        print(f"\nSuccessfully created {num_entities} entities with related records.")

    await engine.dispose()


def main() -> None:
    """Parse arguments and run seed generation."""
    parser = argparse.ArgumentParser(
        description="Generate seed data for LLC Manager development"
    )
    parser.add_argument(
        "--entities",
        type=int,
        default=10,
        help="Number of entities to generate (default: 10)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data before seeding",
    )

    args = parser.parse_args()

    asyncio.run(seed_database(args.entities, args.clear))


if __name__ == "__main__":
    main()
