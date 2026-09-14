// Sondea /progreso/{run_id} y muestra los últimos pasos en vivo. Cuando la
// ejecución termina, redirige a /resultado/{run_id} (éxito o error).
document.addEventListener("DOMContentLoaded", () => {
  const container = document.querySelector("main[data-run-id]");
  if (!container) return;
  const runId = container.dataset.runId;
  const stepsEl = document.getElementById("steps");
  const statusEl = document.getElementById("live-status");
  const detailEl = document.getElementById("live-detail");
  const lostRunActionEl = document.getElementById("lost-run-action");
  const spinnerEl = document.querySelector(".spinner");
  const pollTimeoutMs = 10000;
  let lastStepCount = 0;

  function formatDuration(totalSeconds) {
    const seconds = Math.max(0, Math.floor(totalSeconds || 0));
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    if (minutes <= 0) return `${rest}s`;
    return `${minutes}m ${rest}s`;
  }

  function updateLiveStatus(data) {
    if (!statusEl || !detailEl) return;

    const steps = data.steps || [];
    const latest = steps[steps.length - 1] || "Preparando extraccion";
    const secondsSinceUpdate = data.seconds_since_update || 0;
    const elapsed = data.elapsed_seconds || 0;
    const hasNewStep = steps.length !== lastStepCount;
    lastStepCount = steps.length;

    if (data.done) {
      statusEl.textContent = "Extraccion completada. Preparando resultado...";
      detailEl.textContent = `Tiempo total: ${formatDuration(elapsed)}.`;
      return;
    }

    if (secondsSinceUpdate >= 90) {
      statusEl.textContent = "Sigue trabajando en una fase larga...";
      detailEl.textContent = `Ultimo avance hace ${formatDuration(secondsSinceUpdate)}. Fase actual: ${latest}`;
      return;
    }

    if (secondsSinceUpdate >= 25) {
      statusEl.textContent = "Procesando documentos o respuesta IA...";
      detailEl.textContent = `Sin nuevo hito desde hace ${formatDuration(secondsSinceUpdate)}. Ultimo avance: ${latest}`;
      return;
    }

    statusEl.textContent = hasNewStep ? "Avance recibido" : "Extraccion activa";
    detailEl.textContent = `Tiempo transcurrido: ${formatDuration(elapsed)}. Ultimo avance: ${latest}`;
  }

  async function poll() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), pollTimeoutMs);
    try {
      const resp = await fetch(`/progreso/${runId}`, { signal: controller.signal });
      if (resp.ok) {
        const data = await resp.json();
        updateLiveStatus(data);
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
      } else if (resp.status === 404) {
        if (statusEl) statusEl.textContent = "La ejecucion ya no esta activa";
        if (detailEl) {
          detailEl.textContent =
            "El servidor se ha reiniciado o ha perdido el estado en memoria. Vuelve a la pantalla inicial y lanza la extraccion de nuevo.";
        }
        if (lostRunActionEl) lostRunActionEl.hidden = false;
        if (spinnerEl) spinnerEl.style.animation = "none";
        stepsEl.innerHTML = "";
        return;
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
