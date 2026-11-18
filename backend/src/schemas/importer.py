from pydantic import BaseModel, Field
class ImportSamplePayload(BaseModel):
    code: str=Field(min_length=2,max_length=80)
    title: str=Field(min_length=2,max_length=160)
    quantity: int=Field(ge=1,le=100000)
    location: str=Field(min_length=1,max_length=120)
class ImportTransferPayload(BaseModel):
    code: str=Field(min_length=2,max_length=80)
    destination: str=Field(min_length=2,max_length=120)
    quantity: int=Field(ge=1,le=100000)
    note: str=Field(default='',max_length=300)
class ImportGroupPayload(BaseModel):
    group_ref: str=Field(min_length=1,max_length=80)
    sample: ImportSamplePayload
    transfers: list[ImportTransferPayload]=Field(min_length=1,max_length=50)
class ImportBatchInput(BaseModel):
    batch_no: str=Field(min_length=2,max_length=80)
    groups: list[ImportGroupPayload]=Field(min_length=1,max_length=100)
