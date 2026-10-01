(() => {
  const drawer = document.querySelector("[data-cart-drawer]");
  if (!drawer) return;

  const overlay = document.querySelector("[data-cart-overlay]");
  const rows = document.querySelector("[data-cart-items]");
  const emptyState = document.querySelector("[data-cart-empty]");
  const footer = document.querySelector("[data-cart-footer]");
  const feedback = document.querySelector("[data-cart-feedback]");
  const countLabels = document.querySelectorAll(
    "[data-cart-count], [data-drawer-count]",
  );
  const csrf =
    document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const serverFavorites = new Set(
    (document.body.dataset.favoriteSlugs || "").split(",").filter(Boolean),
  );
  let cart = JSON.parse(
    document.getElementById("initial-cart")?.textContent ||
      '{"items":[],"count":0,"subtotal":"0.00","shipping":"0.00","total":"0.00","free_shipping_threshold":"100.00"}',
  );

  const money = (value) => `$${Number(value).toFixed(2)}`;
  const khr = (value) =>
    `៛${Math.round(Number(value) * Number(cart.khr_per_usd || 4100)).toLocaleString("en-US")}`;

  function setDrawer(open) {
    drawer.classList.toggle("is-open", open);
    overlay.classList.toggle("is-open", open);
    drawer.inert = !open;
    drawer.setAttribute("aria-hidden", String(!open));
    document.body.classList.toggle("drawer-open", open);
    if (open) drawer.querySelector("[data-close-cart]").focus();
  }

  function updateCart(nextCart) {
    cart = nextCart;
    rows.replaceChildren();
    countLabels.forEach((label) => {
      label.textContent = label.hasAttribute("data-drawer-count")
        ? `(${cart.count})`
        : cart.count;
    });
    emptyState.hidden = cart.items.length > 0;
    footer.hidden = cart.items.length === 0;
    document.querySelector("[data-cart-subtotal]").childNodes[0].textContent =
      money(cart.subtotal);
    document.querySelector("[data-cart-subtotal-khr]").textContent = khr(
      cart.subtotal,
    );
    document.querySelector("[data-cart-shipping]").textContent =
      Number(cart.shipping) === 0 ? "Free" : money(cart.shipping);
    const amountLeft =
      Number(cart.free_shipping_threshold) - Number(cart.subtotal);
    document.querySelector("[data-shipping-hint]").textContent =
      amountLeft > 0
        ? `You are ${money(amountLeft)} away from complimentary shipping.`
        : "Your shipping is on us. Lovely choice.";

    cart.items.forEach((item) => {
      const row = document.createElement("article");
      row.className = "cart-row";
      const image = document.createElement("img");
      image.src = item.image_url;
      image.alt = "";
      const main = document.createElement("div");
      main.className = "cart-row-main";
      const name = document.createElement("h3");
      name.textContent = item.name;
      const price = document.createElement("p");
      price.textContent = money(item.price);
      const variantLabel = document.createElement("small");
      variantLabel.className = "variant-label-text";
      variantLabel.textContent = item.variant_label;
      const controls = document.createElement("div");
      controls.className = "quantity-control";
      controls.append(
        quantityButton(
          "−",
          item.slug,
          item.quantity - 1,
          "Decrease quantity",
          item.variant_id,
        ),
        Object.assign(document.createElement("span"), {
          textContent: item.quantity,
        }),
        quantityButton(
          "+",
          item.slug,
          item.quantity + 1,
          "Increase quantity",
          item.variant_id,
        ),
      );
      const remove = document.createElement("button");
      remove.className = "cart-remove";
      remove.type = "button";
      remove.textContent = "Remove";
      remove.addEventListener("click", () =>
        changeQuantity(item.slug, 0, "set", item.variant_id),
      );
      main.append(name, price);
      if (item.variant_label) main.append(variantLabel);
      main.append(controls, remove);
      const total = document.createElement("strong");
      total.className = "cart-row-total";
      total.textContent = money(item.line_total);
      row.append(image, main, total);
      rows.append(row);
    });
  }

  function quantityButton(label, slug, quantity, description, variantId) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.setAttribute("aria-label", description);
    button.addEventListener("click", () =>
      changeQuantity(slug, quantity, "set", variantId),
    );
    return button;
  }

  async function changeQuantity(
    slug,
    quantity,
    action = "set",
    variantId = null,
  ) {
    feedback.textContent = "";
    try {
      const response = await fetch(`/cart/${encodeURIComponent(slug)}/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "Content-Type": "application/x-www-form-urlencoded",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: new URLSearchParams({
          action,
          quantity: String(quantity),
          variant_id: variantId || "",
        }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.error || "That update did not go through.");
      updateCart(result);
      if (action === "add") {
        feedback.textContent = "Added to your bag. Good choice.";
        setDrawer(true);
      }
    } catch (error) {
      feedback.textContent = error.message;
    }
  }

  document
    .querySelectorAll("[data-open-cart]")
    .forEach((button) =>
      button.addEventListener("click", () => setDrawer(true)),
    );
  document
    .querySelectorAll("[data-close-cart]")
    .forEach((button) =>
      button.addEventListener("click", () => setDrawer(false)),
    );
  overlay.addEventListener("click", () => setDrawer(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer.classList.contains("is-open"))
      setDrawer(false);
  });
  document.querySelectorAll("[data-add-to-bag]").forEach((button) => {
    button.addEventListener("click", () =>
      changeQuantity(button.dataset.addToBag, 1, "add"),
    );
  });
  document.querySelectorAll("[data-favorite]").forEach((button) => {
    const key = "swaystudio-favorites";
    const slug = button.dataset.favorite;
    const authenticated = button.dataset.authenticated === "true";
    const favorites = new Set(JSON.parse(localStorage.getItem(key) || "[]"));
    let isFavorite = authenticated
      ? serverFavorites.has(slug)
      : favorites.has(slug);
    button.classList.toggle("is-favorite", isFavorite);
    button.setAttribute("aria-pressed", String(isFavorite));
    button.querySelector("span").textContent = isFavorite ? "♥" : "♡";
    if (!authenticated) {
      button.classList.toggle("is-favorite", favorites.has(slug));
      button.addEventListener("click", () => {
        if (favorites.has(slug)) favorites.delete(slug);
        else favorites.add(slug);
        localStorage.setItem(key, JSON.stringify([...favorites]));
        button.classList.toggle("is-favorite", favorites.has(slug));
        button.setAttribute("aria-pressed", String(favorites.has(slug)));
        button.querySelector("span").textContent = favorites.has(slug)
          ? "♥"
          : "♡";
      });
      return;
    }
    button.addEventListener("click", async () => {
      try {
        const response = await fetch(
          `/favorites/${encodeURIComponent(slug)}/`,
          {
            method: "POST",
            headers: {
              "X-CSRFToken": csrf,
              "X-Requested-With": "XMLHttpRequest",
            },
          },
        );
        if (!response.ok) throw new Error("Could not update saved pieces.");
        const result = await response.json();
        button.classList.toggle("is-favorite", result.favorite);
        button.setAttribute("aria-pressed", String(result.favorite));
        button.querySelector("span").textContent = result.favorite ? "♥" : "♡";
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
  });

  updateCart(cart);
})();
