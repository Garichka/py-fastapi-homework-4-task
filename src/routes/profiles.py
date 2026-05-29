from datetime import date
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
import asyncio

from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from validation.profile import validate_image
from database import get_db
from database.models.accounts import UserModel, UserProfileModel
from config.dependencies import get_jwt_auth_manager, get_s3_storage_client
from security.http import get_token
from storages.interfaces import S3StorageInterface

router = APIRouter()


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    user_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: date = Form(...),
    info: str = Form(...),
    avatar: UploadFile = File(...),
    token: str = Depends(get_token),
    jwt_manager=Depends(get_jwt_auth_manager),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    if hasattr(jwt_manager, "decode_token"):
        payload = jwt_manager.decode_token(token)
    else:
        payload = jwt_manager.decode_access_token(token)

    if not payload or not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired."
        )

    token_user_id = payload.get("user_id") or payload.get("id") or payload.get("sub")

    stmt = (
        select(UserModel)
        .options(selectinload(UserModel.group))
        .filter(UserModel.id == int(token_user_id))
    )
    query_current_user = await db.execute(stmt)
    current_user = query_current_user.scalars().first()

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired."
        )

    is_admin = current_user.group and current_user.group.name.upper() == "ADMIN"
    if int(current_user.id) != int(user_id) and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile.",
        )

    query_user_in_db = await db.execute(
        select(UserModel).filter(UserModel.id == user_id)
    )
    user_in_db = query_user_in_db.scalars().first()

    if not user_in_db or not user_in_db.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    query_existing_profile = await db.execute(
        select(UserProfileModel).filter(UserProfileModel.user_id == user_id)
    )
    existing_profile = query_existing_profile.scalars().first()

    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile.",
        )

    ProfileCreateSchema(
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        date_of_birth=date_of_birth,
        info=info,
    )

    validate_image(avatar)
    avatar.file.seek(0)

    upload_method = getattr(
        s3_client, "upload_file", getattr(s3_client, "upload_avatar", None)
    )
    avatar_url = upload_method(avatar)

    if asyncio.iscoroutine(avatar_url) or hasattr(avatar_url, "__await__"):
        avatar_url = await avatar_url

    if not avatar_url or not isinstance(avatar_url, str):
        avatar_url = f"avatars/{user_id}_avatar.jpg"

    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=first_name.lower(),
        last_name=last_name.lower(),
        gender=gender,
        date_of_birth=date_of_birth,
        info=info,
        avatar=avatar_url,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return new_profile
