// Sondea /progreso/{run_id} y muestra los últimos pasos en vivo. Cuando la
// ejecución termina, redirige a /resultado/{run_id} (éxito o error).
document.addEventListener("DOMContentLoaded", () => {
  const container = document.querySelector("main[data-run-id]");
  if (!container) return;
  const runId = container.dataset.runId;
  const stepsEl = document.getElementById("steps");
  const pollTimeoutMs = 10000;

  async function poll() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), pollTimeoutMs);
    try {
      const resp = await fetch(`/progreso/${runId}`, { signal: controller.signal });
      if (resp.ok) {
        const data = await resp.json();
        stepsEl.innerHTML = "";
        (data.steps || []).slice(-12).forEach((step) => {
          const li = document.createElement("li");
          li.textContent = step;
          stepsEl.appendChild(li);
        });
        if (data.done) {
          window.location.href = `/resultado/${runId}`;
          return;
        }
      }
    } catch (err) {
      // red momentáneamente caída: se reintenta en el siguiente ciclo
    } finally {
      clearTimeout(timeoutId);
    }
    setTimeout(poll, 1500);
  }

  poll();
});
