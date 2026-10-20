document.addEventListener("DOMContentLoaded", () => {
  // Smoothly reveal cards when they enter the viewport.
  const cards = document.querySelectorAll(".event-card, .admin-stat, .dash-panel");
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    cards.forEach(card => { card.classList.add("reveal"); observer.observe(card); });
  }
  // Set a useful minimum date for new event forms.
  const dateInput = document.querySelector('input[name="event_date"]');
  if (dateInput && !dateInput.value) dateInput.min = new Date().toISOString().slice(0, 10);
});
