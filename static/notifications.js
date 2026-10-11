(() => {
    const badges = document.querySelectorAll('[data-unread-notice-count]');
    const toastRegion = document.getElementById('notification-toast-region');
    if (!badges.length || !toastRegion) return;

    let reconnectDelay = 1000;
    let notificationSocket;
    let reconnectTimer;
    let closing = false;

    function updateCount(count) {
        const unreadCount = Number(count) || 0;
        badges.forEach((badge) => {
            badge.textContent = unreadCount > 99 ? '99+' : String(unreadCount);
            badge.hidden = unreadCount === 0;

            const link = badge.closest('a');
            if (link) {
                link.setAttribute('aria-label', `Повідомлення, непрочитаних: ${unreadCount}`);
            }
        });
    }

    function showNotification(notification) {
        const toast = document.createElement('a');
        toast.href = '/messanger/notices/';
        toast.className = 'block max-w-sm rounded-lg bg-slate-900 px-4 py-3 text-sm text-white shadow-lg';
        toast.setAttribute('role', 'status');
        toast.textContent = notification.message;
        toastRegion.appendChild(toast);
        window.setTimeout(() => toast.remove(), 7000);
    }

    function connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        notificationSocket = new WebSocket(`${protocol}//${window.location.host}/ws/notifications/`);

        notificationSocket.onopen = () => {
            reconnectDelay = 1000;
        };

        notificationSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'notification.count') {
                updateCount(data.unread_count);
            } else if (data.type === 'notification.created') {
                updateCount(data.notification.unread_count);
                showNotification(data.notification);
            }
        };

        notificationSocket.onclose = () => {
            if (closing) return;
            reconnectTimer = window.setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 15000);
        };
    }

    window.addEventListener('beforeunload', () => {
        closing = true;
        window.clearTimeout(reconnectTimer);
        if (notificationSocket) notificationSocket.close();
    }, { once: true });

    connect();
})();
