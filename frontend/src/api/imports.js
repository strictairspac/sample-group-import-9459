import {api} from './client.js';
export const importsApi={list:()=>api('/imports'),detail:id=>api('/imports/'+id),submit:data=>api('/imports','POST',data)};
