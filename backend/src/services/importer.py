"""Grouped import: each group (one new sample + its transfer requests) is one atomic unit.

Group outcomes and business writes commit in the same transaction. Already processed
groups are never applied twice; retries with the same batch number and identical
content are idempotent and write neither business rows nor audit entries.
"""
import json,hashlib
from datetime import datetime,timezone
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from redis import Redis
from fastapi import HTTPException
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.entities import ImportBatch,ImportGroup,Sample,Transfer,Audit
from src.utils.serialization import record
from src.constants.enums import IMPORT_GROUP_STATES

queue=Redis.from_url(REDIS_URL,decode_responses=True)
QUEUE_KEY='locklab:import:queue'

def canonical(data): return json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def hash_payload(data): return hashlib.sha256(canonical(data).encode()).hexdigest()

def _validate_request(payload):
    refs,codes,tcodes=set(),set(),set()
    for g in payload['groups']:
        ref=g['group_ref']
        if ref in refs: raise HTTPException(400,f'组号 {ref} 在同一批号内重复')
        refs.add(ref)
        code=g['sample']['code']
        if code in codes: raise HTTPException(400,f'样本编号 {code} 被多个组使用，无法各自成组')
        codes.add(code)
        for t in g['transfers']:
            if t['code'] in tcodes: raise HTTPException(400,f'移交申请编号 {t["code"]} 在导入内容中重复')
            tcodes.add(t['code'])

def submit(db,data,user):
    payload=data.model_dump()
    content_hash=hash_payload(payload)
    _validate_request(payload)
    existing=db.scalar(select(ImportBatch).where(ImportBatch.batch_no==data.batch_no))
    if existing:
        if existing.content_hash!=content_hash:
            raise HTTPException(409,f'批号 {data.batch_no} 已存在且内容不同，禁止覆盖；请使用新批号')
        # Identical retry: no business write and no audit entry. Re-arm any groups
        # still pending so a lost queue message heals itself.
        pending=[g.id for g in db.scalars(select(ImportGroup).where(ImportBatch.id==existing.id,ImportGroup.status=='pending'))]
        if pending: _enqueue(pending)
        return _detail(db,existing.id),True
    # Idempotency is keyed by batch number; content_hash is stored (and indexed)
    # for audit/diff purposes and keeps a full canonical copy of every submission.
    try:
        batch=ImportBatch(batch_no=data.batch_no,content_hash=content_hash,status='processing',
                          group_total=len(payload['groups']),group_committed=0,group_rejected=0,created_by=user.email)
        db.add(batch);db.flush()
        group_ids=[]
        for g in payload['groups']:
            row=ImportGroup(batch_id=batch.id,group_ref=g['group_ref'],sample_code=g['sample']['code'],
                            transfer_count=len(g['transfers']),status=IMPORT_GROUP_STATES[0],
                            content_hash=hash_payload(g),payload=g)
            db.add(row);db.flush();group_ids.append(row.id)
        db.add(Audit(actor=user.email,action=f'成组导入受理 {data.batch_no}（{len(group_ids)} 组）'))
        db.commit()
    except IntegrityError:
        # Concurrent submission of the same batch_no: re-read and apply idempotency rules.
        db.rollback()
        winner=db.scalar(select(ImportBatch).where(ImportBatch.batch_no==data.batch_no))
        if winner is None: raise HTTPException(500,'批次受理冲突，请重试')
        if winner.content_hash!=content_hash:
            raise HTTPException(409,f'批号 {data.batch_no} 已存在且内容不同，禁止覆盖；请使用新批号')
        pending=[g.id for g in db.scalars(select(ImportGroup).where(ImportBatch.id==winner.id,ImportGroup.status=='pending'))]
        if pending: _enqueue(pending)
        return _detail(db,winner.id),True
    _enqueue(group_ids)
    return _detail(db,batch.id),False

def _enqueue(group_ids):
    try:
        for gid in group_ids: queue.lrem(QUEUE_KEY,0,str(gid))
        if group_ids: queue.rpush(QUEUE_KEY,*[str(x) for x in group_ids])
    except Exception:
        raise HTTPException(503,'导入队列不可用，批次已落库；恢复队列后重新提交同批号即可继续')

def listing(db):
    rows=db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())).all()
    return [_summary(db,b) for b in rows]

def detail(db,ident):
    batch=db.get(ImportBatch,ident)
    if not batch: raise HTTPException(404,'导入批次不存在')
    return _detail(db,ident)

def _summary(db,batch):
    out=record(batch)
    out['groups']=[record(g) for g in db.scalars(select(ImportGroup).where(ImportGroup.batch_id==batch.id).order_by(ImportGroup.id))]
    return out

def _detail(db,ident): return _summary(db,db.get(ImportBatch,ident))

def process_group(group_id):
    """Worker entry point. Returns a short status string; never raises for business rejection."""
    with Session() as db:
        # Row lock serializes any duplicate dispatch of the same group id.
        group=db.scalar(select(ImportGroup).where(ImportGroup.id==group_id).with_for_update())
        if group is None: return f'group {group_id} missing, skipped'
        if group.status!='pending': return f'group {group_id} already {group.status}, skipped'
        reason=_apply_group(db,group)
        if reason:
            group.status='rejected';group.reason=reason
        else:
            group.status='committed'
        group.processed_at=datetime.now(timezone.utc)
        _refresh_batch_counters(db,group.batch_id)
        db.commit()
        return f'group {group_id} {group.status}'

class _Rollback(Exception): pass

def _apply_group(db,group):
    payload=group.payload
    # Read-only pre-checks give friendly rejection reasons; the unique indexes
    # remain the hard guarantee against concurrent collisions (caught as 23505).
    sample=db.scalar(select(Sample).where(Sample.code==payload['sample']['code']))
    if sample: return f'样本编号 {payload["sample"]["code"]} 已存在（撞号），保留原记录，整组回滚'
    existing_codes=[t['code'] for t in payload['transfers']
                    if db.scalar(select(Transfer.id).where(Transfer.code==t['code']))]
    if existing_codes: return f'移交申请编号已存在：{"、".join(existing_codes)}，整组回滚'
    sp=payload['sample']
    savepoint=db.begin_nested()
    try:
        new_sample=Sample(code=sp['code'],title=sp['title'],quantity=sp['quantity'],location=sp['location'])
        db.add(new_sample);db.flush()
        for t in payload['transfers']:
            if t['quantity']>sp['quantity']:
                raise _Rollback(f'申请 {t["code"]} 移交 {t["quantity"]} 份超过样本可用量 {sp["quantity"]} 份，整组回滚')
            db.add(Transfer(code=t['code'],sample_id=new_sample.id,destination=t['destination'],
                            quantity=t['quantity'],note=t.get('note','')))
        db.add(Audit(actor=_batch_owner(db,group.batch_id),
                     action=f'成组导入提交 组 {group.group_ref} / 样本 {sp["code"]}（{len(payload["transfers"])} 条申请）'))
        savepoint.commit()
        return ''
    except _Rollback as e:
        savepoint.rollback();return str(e)
    except Exception as e:
        savepoint.rollback()
        state=getattr(getattr(e,'orig',None),'sqlstate',None)
        if state=='23505': return f'编号冲突（SQLSTATE 23505），疑似并发撞号，整组回滚：{e.orig.diag.message_detail if hasattr(e.orig,"diag") else e}'
        if state: return f'数据库错误 SQLSTATE {state}，整组回滚：{e}'
        return f'组处理失败，整组回滚：{e}'

def _batch_owner(db,batch_id):
    return db.scalar(select(ImportBatch.created_by).where(ImportBatch.id==batch_id))

def _refresh_batch_counters(db,batch_id):
    committed=db.scalar(select(func.count()).select_from(ImportGroup).where(ImportGroup.batch_id==batch_id,ImportGroup.status=='committed'))
    rejected=db.scalar(select(func.count()).select_from(ImportGroup).where(ImportGroup.batch_id==batch_id,ImportGroup.status=='rejected'))
    batch=db.get(ImportBatch,batch_id)
    batch.group_committed=committed;batch.group_rejected=rejected
    if committed+rejected>=batch.group_total:
        batch.status='finished';batch.finished_at=datetime.now(timezone.utc)

def requeue_pending():
    """Crash recovery: re-arm every undecided group after a worker restart."""
    with Session() as db:
        ids=[r for r in db.scalars(select(ImportGroup.id).where(ImportGroup.status=='pending').order_by(ImportGroup.id))]
    if ids:
        for gid in ids: queue.lrem(QUEUE_KEY,0,str(gid))
        queue.rpush(QUEUE_KEY,*[str(x) for x in ids])
    return len(ids)
