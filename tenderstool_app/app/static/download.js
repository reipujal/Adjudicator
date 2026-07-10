// Descarga con diálogo nativo "Guardar como" (File System Access API).
// Si el navegador no la soporta (Firefox, Safari, o contexto no seguro),
// cae automáticamente al comportamiento de descarga normal del navegador.
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("download-btn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const filename = btn.dataset.filename;
    const statusEl = document.getElementById("download-status");
    statusEl.style.display = "none";

    try {
      const resp = await fetch(`/descargar/${encodeURIComponent(filename)}`);
      if (!resp.ok) {
        throw new Error("No se pudo obtener el fichero del servidor");
      }
      const blob = await resp.blob();

      if (window.showSaveFilePicker) {
        const handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: [
            {
              description: "Excel",
              accept: {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
              },
            },
          ],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
      } else {
        // Fallback sin diálogo nativo: descarga normal del navegador.
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      if (err.name === "AbortError") return; // el usuario canceló el diálogo
      statusEl.textContent = "Error al descargar: " + err.message;
      statusEl.style.display = "block";
    }
  });
});
