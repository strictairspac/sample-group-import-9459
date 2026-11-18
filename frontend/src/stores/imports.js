import {importsApi} from '../api/imports.js';
export const importsStore={items:[],async refresh(){this.items=await importsApi.list();return this.items;}};
