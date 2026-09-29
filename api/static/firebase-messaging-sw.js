// SurgeSight web push service worker. Served by the API at /firebase-messaging-sw.js with the public config filled in.
importScripts("https://www.gstatic.com/firebasejs/__SDK__/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/__SDK__/firebase-messaging-compat.js");

firebase.initializeApp(__CONFIG__);
const messaging = firebase.messaging();

// Messages that carry a `notification` block are shown by the browser automatically. Data-only messages land here.
messaging.onBackgroundMessage((payload) => {
  if (payload.notification) return;
  const data = payload.data || {};
  self.registration.showNotification(data.title || "SurgeSight exercise", { body: data.body || "", tag: "surgesight" });
});
