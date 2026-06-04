from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyResponse

router = APIRouter()


@router.get("/", response_model=list[CompanyResponse])
async def list_companies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).order_by(Company.is_default.desc(), Company.name))
    return result.scalars().all()


@router.post("/", response_model=CompanyResponse)
async def create_company(data: CompanyCreate, db: AsyncSession = Depends(get_db)):
    company = Company(**data.model_dump())

    # If this is set as default, unset other defaults
    if company.is_default:
        await _clear_defaults(db)

    # If it's the first company, make it default
    count_result = await db.execute(select(Company))
    if not count_result.scalars().first():
        company.is_default = True

    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(company_id: str, data: CompanyUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = data.model_dump(exclude_unset=True)

    # If setting as default, clear other defaults first
    if update_data.get("is_default"):
        await _clear_defaults(db)

    for field, value in update_data.items():
        setattr(company, field, value)

    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/{company_id}")
async def delete_company(company_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    was_default = company.is_default
    await db.delete(company)
    await db.commit()

    # If deleted company was default, set another one as default
    if was_default:
        result = await db.execute(select(Company).order_by(Company.created_at).limit(1))
        next_company = result.scalar_one_or_none()
        if next_company:
            next_company.is_default = True
            await db.commit()

    return {"detail": "Company deleted"}


@router.put("/{company_id}/set-default", response_model=CompanyResponse)
async def set_default_company(company_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    await _clear_defaults(db)
    company.is_default = True
    await db.commit()
    await db.refresh(company)
    return company


async def _clear_defaults(db: AsyncSession):
    """Set is_default=False on all companies."""
    result = await db.execute(select(Company).where(Company.is_default == True))
    for c in result.scalars().all():
        c.is_default = False
