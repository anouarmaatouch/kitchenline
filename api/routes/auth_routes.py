from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from auth import verify_password, create_access_token, get_current_user
from database import get_db
from models_new import User
from schemas import UserLogin, Token, UserOut

# Create router (prefix /api is handled here or in main, let's include it here)
router = APIRouter(prefix="/api", tags=["Auth"])

@router.post("/login", response_model=Token)
async def login(login_data: UserLogin, db: AsyncSession = Depends(get_db)):
    # Async database query
    result = await db.execute(select(User).where(User.username == login_data.username))
    user = result.scalars().first()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create JWT token
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()

@router.post("/profile")
async def update_profile(data: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Update Password if provided
    if 'password' in data and data['password']:
        from auth import get_password_hash
        current_user.password_hash = get_password_hash(data['password'])
        
    # Update Company Settings
    if current_user.company_ref:
        if 'agent_on' in data:
            current_user.company_ref.agent_on = data['agent_on']
        if 'voice' in data:
            current_user.company_ref.voice = data['voice']
        if 'system_prompt' in data:
            current_user.company_ref.system_prompt = data['system_prompt']
        if 'menu' in data:
            current_user.company_ref.menu = data['menu']
            
    await db.commit()
    # Refresh user to get latest state
    # await db.refresh(current_user)
    
    return {"success": True, "user": current_user.to_dict()}
