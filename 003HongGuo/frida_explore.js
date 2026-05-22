// Explore app classes to find video API service
Java.perform(function() {
    console.log("[*] Exploring video player classes...\n");

    // 1. Find all classes related to "player" or "video"
    Java.enumerateLoadedClasses({
        onMatch: function(className) {
            if (className.indexOf("player") >= 0 || className.indexOf("video") >= 0 ||
                className.indexOf("Video") >= 0 || className.indexOf("Player") >= 0 ||
                className.indexOf("vod") >= 0 || className.indexOf("Vod") >= 0 ||
                className.indexOf("VOD") >= 0) {
                console.log("[CLASS] " + className);
            }
        },
        onComplete: function() {
            console.log("\n[*] Class enumeration complete");
        }
    });
});
