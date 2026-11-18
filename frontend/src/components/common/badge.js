import {RUN_STATES,IMPORT_BATCH_STATES,IMPORT_GROUP_STATES} from '../../constants/enums.js';
import {esc} from '../../utils/html.js';
const maps={...RUN_STATES,...IMPORT_BATCH_STATES,...IMPORT_GROUP_STATES};
export const badge=value=>`<span class="badge ${esc(value)}">${esc(maps[value]||value)}</span>`;
