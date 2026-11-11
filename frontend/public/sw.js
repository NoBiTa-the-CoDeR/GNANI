// No remote push, contact access, or fetch caching. Reminders are scheduled
// by an open page; a service worker cannot reliably wake a closed browser.
self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil((async()=>{const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});if(windows.length){await windows[0].focus();return}await self.clients.openWindow('/')})())});
