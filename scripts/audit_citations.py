"""Audit citation traceability across the PostgreSQL corpus."""

import asyncio

from sqlalchemy import select

from nikshaynavigator.config import Settings
from nikshaynavigator.db.models import Document, Page
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.ingest.citations import audit_citations


async def main() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    try:
        async with session_factory() as session:
            documents = list(
                (await session.scalars(select(Document).order_by(Document.id))).all()
            )

            pages = list(
                (
                    await session.scalars(
                        select(Page).order_by(Page.document_id, Page.page_no)
                    )
                ).all()
            )

        report = audit_citations(documents, pages)

        print("\nCITATION TRACEABILITY REPORT")
        print("-" * 40)
        print(f"Documents:       {len(documents)}")
        print(f"Pages checked:   {report.pages_checked}")
        print(f"Valid pages:     {report.valid_pages}")
        print(f"Invalid pages:   {report.invalid_pages}")
        print(f"Coverage:        {report.coverage_percent}%")
        print(f"Issues found:    {len(report.issues)}")

        for issue in report.issues[:30]:
            print(
                f"[{issue.code}] "
                f"Document={issue.document_id}, "
                f"Page={issue.page_no}: {issue.detail}"
            )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
