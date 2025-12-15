self.addEventListener('push', function(event) {
    let data = {};
    if (event.data) {
        data = event.data.json();
    }
    
    const options = {
        body: data.message || "New Notification",
        icon: 'https://cdn-icons-png.flaticon.com/512/3081/3081840.png',
        badge: 'https://cdn-icons-png.flaticon.com/512/3081/3081840.png',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: 1
        },
        actions: [
            {action: 'explore', title: 'Voir Commandes', icon: 'checkmark.png'},
            {action: 'close', title: 'Fermer', icon: 'xmark.png'},
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title || 'Restaurant AI', options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow('/')
    );
});
