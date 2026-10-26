// Experimental read-only projection; not connected to the production worker.
// JSON text operators preserve numeric lexemes and JSON types. Duplicate selected
// keys fall back to the full row so JSON.parse retains its last-key-wins behavior.
export const VERSION='statistics-projection-1';
const FIELDS={
 alerts:{plain:['id','legacy','engineVersion'],nested:{candidate:['mint'],qualification:['version','disposition','state']}},
 outcomes:{plain:['version','mint','alertAt','horizon','status','coverage','multiple','maxMultiple','score','entryMarketCap'],nested:{}},
 'research-entries':{plain:['id','at','version','cohort'],nested:{}},
 'research-outcomes':{plain:['entryId','horizon','status','returnPct','coverage','reasonCode'],nested:{tokenFollowup:['status','returnPct','coverage','basis']}}
};
const list=keys=>keys.map(k=>`'${k}'`).join(',');
export function projectionSql(kind){
 const spec=FIELDS[kind];if(!spec)throw Error('unsupported-summary-kind');
 const keys=[...spec.plain,...Object.keys(spec.nested)];
 const duplicates=[`(SELECT count(*)!=count(DISTINCT key) FROM json_each(e.data) WHERE key IN (${list(keys)}))`];
 const branches=[];
 for(const [name,fields] of Object.entries(spec.nested)){
  duplicates.push(`(SELECT count(*)!=count(DISTINCT key) FROM json_each(e.data,'$.${name}') WHERE key IN (${list(fields)}))`);
  const nested=`(SELECT json_group_object(n.key,json(e.data -> n.fullkey)) FROM json_each(e.data,'$.${name}') AS n WHERE n.key IN (${list(fields)}))`;
  branches.push(`WHEN '${name}' THEN CASE WHEN r.type='object' THEN json(${nested}) ELSE json(e.data -> r.fullkey) END`);
 }
 const value=branches.length?`CASE r.key ${branches.join(' ')} ELSE json(e.data -> r.fullkey) END`:'json(e.data -> r.fullkey)';
 const compact=`(SELECT json_group_object(r.key,${value}) FROM json_each(e.data) AS r WHERE r.key IN (${list(keys)}))`;
 return `SELECT e.seq,length(CAST(e.data AS BLOB)) AS rawBytes,
 CASE WHEN length(CAST(e.data AS BLOB))>262144 THEN NULL
 WHEN json_valid(e.data) THEN CASE WHEN json_type(e.data)!='object' OR ${duplicates.join(' OR ')} THEN e.data ELSE ${compact} END
 ELSE NULL END AS data
 FROM events AS e WHERE e.kind=? ORDER BY e.seq`.replaceAll('json_each(e.data','json_each(jsonb(e.data)').replaceAll('e.data ->','jsonb(e.data) ->');
}
export function projectedStatement(db,kind){return db.prepare(projectionSql(kind));}
