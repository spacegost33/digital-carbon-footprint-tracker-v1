"use strict";

let installPrompt = null;

const installButton = document.getElementById(
    "installAppButton"
);

window.addEventListener(
    "beforeinstallprompt",
    (event) => {
        event.preventDefault();

        installPrompt = event;

        if (installButton) {
            installButton.style.removeProperty("display");
        }
    }
);

if (installButton) {
    installButton.addEventListener(
        "click",
        async () => {
            if (!installPrompt) {
                return;
            }

            try {
                await installPrompt.prompt();

                const result =
                    await installPrompt.userChoice;

                console.log(
                    "Installation:",
                    result.outcome
                );
            } catch (error) {
                console.error(
                    "Installation failed:",
                    error
                );
            } finally {
                installPrompt = null;
                installButton.style.display = "none";
            }
        }
    );
}

window.addEventListener("appinstalled", () => {
    installPrompt = null;

    if (installButton) {
        installButton.style.display = "none";
    }

    console.log("CarbonTrack installed.");
});

if (
    window.matchMedia(
        "(display-mode: standalone)"
    ).matches
) {
    if (installButton) {
        installButton.style.display = "none";
    }
}