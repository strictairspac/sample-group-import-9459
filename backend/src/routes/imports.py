from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.importer import ImportBatchInput
from src.services import importer as service
router=APIRouter()
@router.get('/imports')
def listing(db=Depends(db_session),user=Depends(current)): return service.listing(db)
@router.get('/imports/{ident}')
def detail(ident:int,db=Depends(db_session),user=Depends(current)): return service.detail(db,ident)
@router.post('/imports',status_code=202)
def submit(data:ImportBatchInput,db=Depends(db_session),user=Depends(writer)):
    body,idempotent=service.submit(db,data,user)
    body['idempotent_retry']=idempotent
    return body
