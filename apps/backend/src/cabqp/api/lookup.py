from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.modules.resolution.service import Resolver
from cabqp.shared.db import get_db
from cabqp.shared.schemas import LookupRequest

router = APIRouter(prefix="/lookup", tags=["lookup"])


@router.post("/unit")
def lookup_unit(
    body: LookupRequest,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.LOOKUP_UNIT)),
):
    return Resolver(db).resolve(body.unit_name, body.unit_code, body.as_of_date).__dict__
