import time,traceback,json,os
from pathlib import Path
from src.config.database import Session
from src.models.entities import Trial
from src.services.trials import queue
from src.services.concurrency import execute
from src.services import importer
ARTIFACT_DIR=Path(os.getenv('ARTIFACT_DIR','/artifacts'))
ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
TRIAL_QUEUE='locklab:queue'
# Crash recovery: groups still pending after a restart are re-armed immediately.
recovered=importer.requeue_pending()
print(f'import recovery: {recovered} pending groups re-queued',flush=True)
last_recover=time.time()
while True:
    Path('/tmp/worker-heartbeat').touch()
    item=queue.blpop([TRIAL_QUEUE,importer.QUEUE_KEY],timeout=2)
    if not item:
        # Self-heal a lost queue message at most once every 30s while idle.
        if time.time()-last_recover>30:
            importer.requeue_pending();last_recover=time.time()
        continue
    key,payload=item
    try:
        if key==importer.QUEUE_KEY:
            print(importer.process_group(int(payload)),flush=True)
            continue
        ident=int(payload)
        result=execute(ident)
        (ARTIFACT_DIR/f'trial-{ident}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception:
        traceback.print_exc()
        if key==TRIAL_QUEUE:
            with Session() as db:
                obj=db.get(Trial,ident)
                if obj: obj.status='failed';obj.error='worker 执行失败，请重建演练';db.commit()
