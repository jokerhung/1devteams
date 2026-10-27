self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/notifications", self.location.origin);
  if (url.origin !== self.location.origin) return;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const existing = windows.find((client) => new URL(client.url).origin === url.origin);
    if (existing) {
      await existing.navigate(url.href);
      await existing.focus();
    } else {
      await self.clients.openWindow(url.href);
    }
  })());
});
