export function imageQueries(panel){
 const queries=(panel.image_queries||[]).filter(x=>typeof x==='string'&&x.trim()).slice(0,3);
 if(queries.length)return queries;
 // A title-derived search still provides useful visual help when the model
 // omits its optional photo queries. The service may honestly return no photos.
 const title=(panel.title||'').replace(/^how\s+to\s+(?:make\s+)?/i,'').trim();
 return title?[title.slice(0,80)]:[];
}
export function videoQuery(panel,lang='en'){
 if(panel.video_query)return panel.video_query.slice(0,100);
 if(!['recipe','howto'].includes(panel.kind)||!panel.title)return '';
 return (panel.title+(lang.startsWith('hi')?' वीडियो':lang.startsWith('kn')?' ವಿಡಿಯೋ':' step by step tutorial')).slice(0,100);
}
