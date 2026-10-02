document.documentElement.classList.add("js");

// Ask for confirmation before submitting any form marked with data-confirm.
document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});

// Submit the form as soon as a select marked with data-autosubmit changes.
document.addEventListener("change", function (event) {
    var el = event.target;
    if (el.hasAttribute && el.hasAttribute("data-autosubmit") && el.form) {
        el.form.submit();
    }
});

// Give focused controls a little extra accessibility support without
// changing the existing form behaviour.
document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && document.activeElement) {
        document.activeElement.blur();
    }
});
