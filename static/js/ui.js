console.log("Smart Waste UI loaded");


// ===============================
// ACTIVE NAVIGATION HIGHLIGHT
// ===============================

const currentPath = window.location.pathname;

document.querySelectorAll(".nav-link-btn").forEach(link => {

    if (link.getAttribute("href") === currentPath) {

        link.classList.add("active");

    }

});


// ===============================
// SYSTEM INITIALIZATION TOAST
// ===============================

document.addEventListener("DOMContentLoaded", function(){


    if (!sessionStorage.getItem("systemToastShown")) {


        const toast = document.createElement("div");

        toast.className = "system-toast";


        toast.innerHTML = `

            <div class="toast-icon">
                🟢
            </div>

            <div>

                <strong>
                    Smart Waste System Active
                </strong>

                <br>

                <small>
                    Monitoring interface initialized successfully
                </small>

            </div>

        `;


        document.body.appendChild(toast);



        setTimeout(() => {

            toast.classList.add("show");

        },200);



        setTimeout(() => {

            toast.classList.remove("show");


        },4500);



        setTimeout(() => {

            toast.remove();


        },5200);



        sessionStorage.setItem(
            "systemToastShown",
            "true"
        );


    }


});