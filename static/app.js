// Progressive enhancements: the site works fully without JavaScript.
(() => {
  const input = document.getElementById("q");
  const list = document.getElementById("completions");
  if (!input) return;

  // Press "/" anywhere to jump to the search box.
  document.addEventListener("keydown", (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      input.focus();
      input.select();
    }
  });

  // Autocomplete the last word from the index vocabulary.
  if (!list) return;
  let timer = 0;
  let controller = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const value = input.value;
      if (!value.trim()) {
        list.replaceChildren();
        return;
      }
      controller?.abort();
      controller = new AbortController();
      try {
        const response = await fetch(`/api/complete?q=${encodeURIComponent(value)}`, {
          signal: controller.signal,
        });
        if (!response.ok) return;
        const options = (await response.json()).map((text) => {
          const option = document.createElement("option");
          option.value = text;
          return option;
        });
        list.replaceChildren(...options);
      } catch (error) {
        if (error.name !== "AbortError") list.replaceChildren();
      }
    }, 120);
  });
})();
