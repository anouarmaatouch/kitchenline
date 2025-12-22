from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func
from typing import List, Optional

from database import get_db
from models_new import Order, Demand, User, Company, MenuImage
from auth import get_current_user, get_current_admin_user, get_password_hash
from schemas import OrderOut, DemandOut, CompanyOut, UserOut
from utils.phone import normalize_phone
from config.constants import DEFAULT_SYSTEM_PROMPTS

# We split into two routers or keep one with prefix /api
# Frontend calls /api/dashboard, /api/demands, etc.
# But some are /api/admin/...
# I will use one router and specify paths manually to match legacy structure exactly.

router = APIRouter(prefix="/api", tags=["Admin"])

# --- Dashboard & Orders ---

@router.get("/dashboard")
async def dashboard(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Filter Logic
    if current_user.company_id:
        filter_kwargs = {"company_id": current_user.company_id}
    else:
        # Superadmin sees all? Or empty? Legacy behavior: If no company, see all if superadmin.
        if current_user.is_superadmin:
             filter_kwargs = {}
        else:
             return {"orders_recu": [], "orders_en_cours": [], "orders_termine": []}

    async def get_orders(status):
        stmt = select(Order).filter_by(status=status, **filter_kwargs).order_by(desc(Order.created_at))
        result = await db.execute(stmt)
        return result.scalars().all()

    return {
        "orders_recu": await get_orders("recu"),
        "orders_en_cours": await get_orders("en_cours"),
        "orders_termine": await get_orders("termine")
    }

@router.get("/demands")
async def get_demands(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.is_superadmin:
        stmt = select(Demand).order_by(desc(Demand.created_at))
    elif current_user.company_id:
        stmt = select(Demand).filter_by(company_id=current_user.company_id).order_by(desc(Demand.created_at))
    else:
        return {"demands_new": [], "demands_processed": []}
        
    result = await db.execute(stmt)
    all_demands = result.scalars().all()
    
    # Enrich with active orders count?
    # For now return list, frontend might expect 'active_orders_count' in objects.
    # We'll skip complex count logic for MVP speed unless vital.
    
    return {
        "demands_new": [d for d in all_demands if d.status == 'new'],
        "demands_processed": [d for d in all_demands if d.status == 'processed']
    }

@router.post("/demands/{demand_id}/status")
async def update_demand_status(demand_id: int, payload: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Demand).where(Demand.id == demand_id))
    demand = result.scalars().first()
    if not demand:
        raise HTTPException(404, "Demand not found")
        
    status_val = payload.get("status")
    if status_val in ['new', 'processed']:
        demand.status = status_val
        await db.commit()
        return {"success": True}
    raise HTTPException(400, "Invalid status")

@router.delete("/demands/{demand_id}")
async def delete_demand(demand_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Demand).where(Demand.id == demand_id))
    demand = result.scalars().first()
    if not demand:
        raise HTTPException(404, "Demand not found")
    
    await db.delete(demand)
    await db.commit()
    return {"success": True}

@router.post("/orders/{order_id}/status")
async def update_order_status(order_id: int, payload: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalars().first()
    if not order:
        raise HTTPException(404, "Order not found")
        
    status_val = payload.get("status")
    if status_val in ['recu', 'en_cours', 'termine']:
        order.status = status_val
        await db.commit()
        return {"success": True, "status": status_val}
    raise HTTPException(400, "Invalid status")

@router.delete("/orders/{order_id}")
async def delete_order(order_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalars().first()
    if not order:
        raise HTTPException(404, "Order not found")
    await db.delete(order)
    await db.commit()
    return {"success": True}

@router.post("/toggle_agent")
async def toggle_agent(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not current_user.company_id:
        raise HTTPException(400, "No company associated")
    
    # Re-fetch company to be sure attached to session
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalars().first()
    
    if company:
        company.agent_on = not company.agent_on
        await db.commit()
        return {"success": True, "agent_on": company.agent_on}
    return {"error": "Company not found"}, 404

# --- Admin Menu ---

@router.get("/admin/menu/image/{image_id}")
async def get_menu_image(image_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MenuImage).where(MenuImage.id == image_id))
    image = result.scalars().first()
    if not image:
        raise HTTPException(404, "Image not found")
        
    return Response(content=image.image_data, media_type="image/jpeg")

@router.post("/admin/menu/save")
async def save_menu_images(
    user_id: int = Form(...),
    menu_images: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_admin_user), # Admin only
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalars().first()
    if not target_user or not target_user.company_id:
        raise HTTPException(404, "User or company not found")
        
    for file in menu_images:
        content = await file.read()
        if content:
            new_img = MenuImage(
                company_id=target_user.company_id,
                image_data=content,
                filename=file.filename
            )
            db.add(new_img)
            
    await db.commit()
    return {"success": True}

@router.get("/admin/users")
async def get_users(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not current_user.is_superadmin:
         raise HTTPException(status_code=403, detail="Superadmin access required")
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [u.to_dict() for u in users]

@router.post("/admin/users")
async def manage_users(payload: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not current_user.is_superadmin:
         raise HTTPException(status_code=403, detail="Superadmin access required")

    action = payload.get('action')
    
    if action == 'create':
        username = payload.get('username')
        result = await db.execute(select(User).where(User.username == username))
        if result.scalars().first():
            raise HTTPException(400, "Cet utilisateur existe déjà")
            
        company_name = payload.get('company')
        phone = payload.get('phone')
        
        new_company = Company(
            name=company_name,
            phone_number=normalize_phone(phone) if phone else None,
            voice='Charon',
            agent_on=True,
            system_prompt=DEFAULT_SYSTEM_PROMPTS.get('fr')
        )
        db.add(new_company)
        await db.flush()
        
        try:
            new_user = User(
                username=username,
                company_id=new_company.id,
                is_admin=payload.get('is_admin', False),
                is_superadmin=payload.get('is_superadmin', False)
            )
            new_user.password_hash = get_password_hash(payload.get('password'))
            
            db.add(new_user)
            await db.commit()
            return {"success": True, "user": new_user.to_dict()}
        except Exception as e:
            print(f"Error creating user: {str(e)}")
            await db.rollback()
            raise HTTPException(500, f"Error creating user: {str(e)}")
        
    elif action == 'edit':
        user_id = payload.get('user_id')
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(404, "User not found")
            
        if 'is_admin' in payload:
             user.is_admin = payload.get('is_admin')
             
        if user.company_ref:
             if 'company' in payload: user.company_ref.name = payload.get('company')
             if 'phone_number' in payload: user.company_ref.phone_number = normalize_phone(payload.get('phone_number'))
             if 'voice' in payload: user.company_ref.voice = payload.get('voice')
             if 'agent_on' in payload: user.company_ref.agent_on = payload.get('agent_on')
             if 'system_prompt' in payload: user.company_ref.system_prompt = payload.get('system_prompt')
             if 'menu' in payload: user.company_ref.menu = payload.get('menu')
        
        await db.commit()
        return {"success": True, "user": user.to_dict()}
        
    elif action == 'delete':
        user_id = payload.get('user_id')
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user:
             await db.delete(user)
             await db.commit()
        return {"success": True}
        
    raise HTTPException(400, "Invalid action")

@router.get("/admin/menu/images")
async def get_menu_images_list(user_id: Optional[int] = None, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    target_company_id = None
    if user_id:
        if not current_user.is_superadmin and current_user.id != user_id:
             raise HTTPException(403, "Access denied")
        result = await db.execute(select(User).where(User.id == user_id))
        target_user = result.scalars().first()
        if target_user and target_user.company_id:
             target_company_id = target_user.company_id
    elif current_user.company_id:
        target_company_id = current_user.company_id
        
    if not target_company_id:
         return []
         
    result = await db.execute(select(MenuImage).filter_by(company_id=target_company_id))
    images = result.scalars().all()
    return [{'id': img.id, 'filename': img.filename} for img in images]

@router.delete("/admin/menu/image/{image_id}")
async def delete_menu_image_endpoint(image_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MenuImage).where(MenuImage.id == image_id))
    image = result.scalars().first()
    if not image:
         raise HTTPException(404, "Image not found")
         
    if not current_user.is_superadmin:
         if image.company_id != current_user.company_id:
              raise HTTPException(403, "Access denied")
              
    await db.delete(image)
    await db.commit()
    return {"success": True}
