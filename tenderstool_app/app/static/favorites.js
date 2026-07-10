// Carga dinámica del desplegable de favoritos: pide a /favoritos la lista
// real del módulo elegido (AJAX, sin salir de la página, sin que la
// password abandone este formulario).
document.addEventListener("DOMContentLoaded", () => {
  const loadBtn = document.getElementById("load-favorites-btn");
  const favoriteSelect = document.getElementById("favorite_select");
  const submitBtn = document.getElementById("submit-btn");
  const errorEl = document.getElementById("favorites-error");
  const searchTypeRadios = document.querySelectorAll('input[name="search_type"]');

  if (!loadBtn || !favoriteSelect) return;

  function resetFavorites() {
    favoriteSelect.innerHTML = '<option value="">— Carga primero los favoritos —</option>';
    favoriteSelect.disabled = true;
    submitBtn.disabled = true;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.style.display = "block";
  }

  searchTypeRadios.forEach((radio) => radio.addEventListener("change", resetFavorites));

  loadBtn.addEventListener("click", async () => {
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const checked = document.querySelector('input[name="search_type"]:checked');
    const searchType = checked ? checked.value : "";

    errorEl.style.display = "none";

    if (!username || !password) {
      showError("Rellena usuario y password antes de cargar favoritos.");
      return;
    }

    loadBtn.disabled = true;
    const originalText = loadBtn.textContent;
    loadBtn.textContent = "Cargando…";

    try {
      const resp = await fetch("/favoritos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, search_type: searchType }),
      });
      const data = await resp.json();

      if (!resp.ok) {
        showError(data.error || "No se pudieron cargar los favoritos.");
        resetFavorites();
        return;
      }

      favoriteSelect.innerHTML = "";
      if (!data.favorites || data.favorites.length === 0) {
        favoriteSelect.innerHTML = '<option value="">No hay favoritos guardados en este módulo</option>';
        favoriteSelect.disabled = true;
        submitBtn.disabled = true;
        return;
      }

      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "— Elige un favorito —";
      favoriteSelect.appendChild(placeholder);

      data.favorites.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        favoriteSelect.appendChild(opt);
      });
      favoriteSelect.disabled = false;
    } catch (err) {
      showError("Error de red al cargar favoritos: " + err.message);
      resetFavorites();
    } finally {
      loadBtn.disabled = false;
      loadBtn.textContent = originalText;
    }
  });

  favoriteSelect.addEventListener("change", () => {
    submitBtn.disabled = !favoriteSelect.value;
  });
});
