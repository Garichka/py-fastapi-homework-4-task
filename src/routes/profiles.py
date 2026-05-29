from datetime import date
from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    Form,
    HTTPException,
    status,
    Header,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import ValidationError

from config.dependencies import get_jwt_auth_manager, get_s3_storage_client
from database import get_db
from database.models.accounts import UserModel, UserProfileModel
from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from storages.interfaces import S3StorageInterface
from validation.profile import validate_image

router = APIRouter()


async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
    jwt_manager=Depends(get_jwt_auth_manager),
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is missing")
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'",
        )
    token = authorization.split(" ")[1]
    try:
        payload = (
            jwt_manager.decode_token(token)
            if hasattr(jwt_manager, "decode_token")
            else jwt_manager.decode_access_token(token)
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Token has expired.")

    user_id = int(payload.get("user_id") or payload.get("sub"))
    user = (
        (
            await db.execute(
                select(UserModel)
                .options(selectinload(UserModel.group))
                .filter(UserModel.id == user_id)
            )
        )
        .scalars()
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="Token has expired.")
    return user


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    user_id: int,
    current_user: UserModel = Depends(get_current_user),
    first_name: str = Form(...),
    last_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: date = Form(...),
    info: str = Form(...),
    avatar: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    is_admin = current_user.group and current_user.group.name.upper() == "ADMIN"
    if current_user.id != user_id and not is_admin:
        raise HTTPException(
            status_code=403, detail="You don't have permission to edit this profile."
        )

    user_in_db = (
        (await db.execute(select(UserModel).filter(UserModel.id == user_id)))
        .scalars()
        .first()
    )
    if not user_in_db or not user_in_db.is_active:
        raise HTTPException(status_code=401, detail="User not found or not active.")

    if (
        (
            await db.execute(
                select(UserProfileModel).filter(UserProfileModel.user_id == user_id)
            )
        )
        .scalars()
        .first()
    ):
        raise HTTPException(status_code=400, detail="User already has a profile.")

    try:
        data = ProfileCreateSchema(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
        )
    except ValidationError as e:
        msg = e.errors()[0]["msg"].replace("Value error, ", "")
        if "Info cannot be empty" in msg:
            msg = "Info field cannot be empty or contain only spaces."
        raise HTTPException(status_code=422, detail=msg)

    try:
        validate_image(avatar)
        avatar_data = await avatar.read()

        file_key = f"avatars/{user_id}_avatar.jpg"

        avatar_url = await s3_client.upload_file(file_key, avatar_data)
    except Exception as e:
        if isinstance(e, ValueError):
            raise HTTPException(status_code=422, detail=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to upload avatar. Please try again later."
        )

    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=data.first_name.lower(),
        last_name=data.last_name.lower(),
        gender=data.gender.lower(),
        date_of_birth=data.date_of_birth,
        info=data.info,
        avatar=str(avatar_url),
    )

    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)
    return new_profile
