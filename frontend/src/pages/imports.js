import {badge} from '../components/common/badge.js';
import {esc,date} from '../utils/html.js';
import {session} from '../hooks/session.js';
const TEMPLATE=JSON.stringify({
  batch_no:'BATCH-261118-01',
  groups:[{
    group_ref:'G1',
    sample:{code:'QY-261118-D',title:'地表水复测留样',quantity:100,location:'冷藏间 A-09'},
    transfers:[
      {code:'MOVE-1118-01',destination:'理化检测室',quantity:30,note:'交接班复核'},
      {code:'MOVE-1118-02',destination:'复核室',quantity:10,note:''}
    ]
  }]
},null,2);
function groupRows(groups){return groups.map(g=>`<tr><td><b>${esc(g.group_ref)}</b></td><td><strong>${esc(g.sample_code)}</strong><small>${g.transfer_count} 条申请</small></td><td>${badge(g.status)}</td><td class="reason">${g.status==='rejected'?esc(g.reason):(g.processed_at?date(g.processed_at):'等待 worker 处理')}</td></tr>`).join('');}
export function importsPage(batches){return `<div class="split"><section><div class="section-top"><h2>成组导入批次</h2><span>${batches.length} 批 / 组级结论</span></div>${batches.length?batches.map(b=>`<article class="batch-card"><div class="batch-head"><div><strong>${esc(b.batch_no)}</strong>${badge(b.status)}<small>提交人 ${esc(b.created_by)} · ${date(b.created_at)}${b.finished_at?' · 结束于 '+date(b.finished_at):''}</small></div><div class="batch-count"><b>${b.group_committed}</b> 入库 / <b>${b.group_rejected}</b> 拒绝 / 共 ${b.group_total} 组</div></div><div class="table-wrap"><table><thead><tr><th>组号</th><th>样本编号</th><th>结论</th><th>拒绝原因 / 处理时间</th></tr></thead><tbody>${groupRows(b.groups)}</tbody></table></div></article>`).join(''):'<div class="empty">还没有导入批次。将交接补录整理为 JSON，从右侧提交；每组是一个新样本加其移交申请，整组同成同败。</div>'}<div class="notice">同组任一申请出错，样本与申请整组回滚，其余组继续；同批号同内容重传不重复写入、不记审计，改内容将被拒绝。</div></section><section class="form-panel"><span class="eyebrow">GROUP IMPORT</span><h2>成组导入移交补录</h2><form id="import-form"><label>批号 + 分组内容（JSON，行顺序不限）<textarea name="payload" rows="16" spellcheck="false" required>${esc(TEMPLATE)}</textarea></label><label>或选择 JSON 文件载入<input id="import-file" type="file" accept="application/json,.json"></label><button type="button" id="import-template" class="ghost">恢复示例模板</button><button class="primary" ${session.user.role==='viewer'?'disabled':''}>提交成组导入 ↗</button></form><p class="help">按样本编号关联各组的新样本与移交申请；并发撞号的组拒绝并保留原记录。处理中页面自动刷新，已处理组立即可在台账与申请簿查询。</p></section></div>`;}
export {TEMPLATE};
