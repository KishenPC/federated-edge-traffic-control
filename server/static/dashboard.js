(function () {
  "use strict";

  const statusBox = document.getElementById("status-box");

  async function loadStatus() {
    try {
      const response = await fetch("/status");
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();
      statusBox.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      statusBox.textContent =
        "Status unavailable.\n\nMake sure the Flask server is running before loading the dashboard.\n\n" +
        String(error.message || error);
    }
  }

  loadStatus();
})();
