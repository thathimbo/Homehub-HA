// Register Service Worker for PWA
(function(){
    // Not inside Home Assistant: its ingress path changes between sessions, so cached pages would go stale
    if ('serviceWorker' in navigator && !window.HH_BASE) {
        window.addEventListener('load', function(){
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .catch(function(err){ console.warn('SW registration failed', err); });
        });
    }
})();
