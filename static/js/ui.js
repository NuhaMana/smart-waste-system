console.log("Smart Waste UI loaded");

const currentPath = window.location.pathname;

document.querySelectorAll(".nav-link-btn").forEach(link => {

    if (link.getAttribute("href") === currentPath) {

        link.classList.add("active");

    }

});