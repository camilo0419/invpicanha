const menuButton = document.querySelector(".menu-btn");
if (menuButton) {
  menuButton.addEventListener("click", () => {
    const open = document.body.classList.toggle("menu-open");
    menuButton.setAttribute("aria-expanded", String(open));
  });
}

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

const inventoryForm = document.querySelector("#inventory-form");
if (inventoryForm) {
  const quantities = [...inventoryForm.querySelectorAll(".quantity-input")];
  const count = document.querySelector("#progress-count");
  const progress = document.querySelector("#progress-bar");
  const search = document.querySelector("#product-search");
  const category = document.querySelector("#category-filter");
  const rows = [...document.querySelectorAll(".product-row")];

  const refreshProgress = () => {
    const filled = quantities.filter((input) => input.value.trim() !== "").length;
    count.textContent = `${filled}/${quantities.length}`;
    progress.value = filled;
  };
  const filterRows = () => {
    const query = (search.value || "").trim().toLowerCase();
    const selectedCategory = category.value;
    rows.forEach((row) => {
      const visible = row.dataset.product.includes(query) &&
        (!selectedCategory || row.dataset.category === selectedCategory);
      row.hidden = !visible;
    });
    document.querySelectorAll(".category-title").forEach((title) => {
      let next = title.nextElementSibling;
      let hasVisible = false;
      while (next && !next.classList.contains("category-title")) {
        if (next.classList.contains("product-row") && !next.hidden) hasVisible = true;
        next = next.nextElementSibling;
      }
      title.hidden = !hasVisible;
    });
  };

  quantities.forEach((input) => {
    input.addEventListener("input", () => {
      input.value = input.value.replace(/[^0-9.,]/g, "");
      refreshProgress();
    });
  });
  search.addEventListener("input", filterRows);
  category.addEventListener("change", filterRows);
  inventoryForm.querySelector(".js-finalize").addEventListener("click", (event) => {
    if (!window.confirm("¿Finalizar y bloquear este inventario? Verifica que todas las cantidades estén completas.")) {
      event.preventDefault();
    }
  });
  refreshProgress();
}
