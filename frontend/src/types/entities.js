/** Sample:{id,code,title,quantity,location}; Transfer:{id,code,sample_id,destination,quantity,note}; Trial:{id,name,transfer_id,timeout_ms,status,result,error}
 *  ImportBatch:{id,batch_no,content_hash,status,group_total,group_committed,group_rejected,groups:ImportGroup[]}
 *  ImportGroup:{id,batch_id,group_ref,sample_code,transfer_count,status(pending|committed|rejected),reason,payload,processed_at} */
export const entityNames=['samples','transfers','trials','importBatches','importGroups'];
